"""
TDD — P1 streaming SSE + P2 X-Provider header (v0.5.0)
+ Phase A v0.6.0 — _safe_stream guarantees [DONE] + error chunks
"""

from __future__ import annotations

import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from main import app
from core.models import ChatResponse, ChatChoice, ChatUsage, Message
from providers.base import ProviderResult, ProviderError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _sse_gen(*lines: str):
    for line in lines:
        yield line


def make_sse_gen():
    return _sse_gen(
        'data: {"id":"c1","object":"chat.completion.chunk","model":"llama","choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":null}]}\n\n',
        "data: [DONE]\n\n",
    )


def mock_non_streaming_result() -> ProviderResult:
    return ProviderResult(
        response=ChatResponse(
            id="abc123",
            model="llama-3.3-70b",
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role="assistant", content="Hello!"),
                    finish_reason="stop",
                )
            ],
            usage=ChatUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
        ),
        provider_name="groq",
        tokens_used=8,
    )


# ---------------------------------------------------------------------------
# Streaming tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_returns_200():
    with patch("routes.chat.get_router") as mock_get:
        r_mock = MagicMock()
        r_mock.route_stream = AsyncMock(return_value=("groq", make_sse_gen()))
        mock_get.return_value = r_mock

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
            )

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_streaming_content_type_event_stream():
    with patch("routes.chat.get_router") as mock_get:
        r_mock = MagicMock()
        r_mock.route_stream = AsyncMock(return_value=("groq", make_sse_gen()))
        mock_get.return_value = r_mock

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
            )

    assert "text/event-stream" in r.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_streaming_has_x_provider_header():
    with patch("routes.chat.get_router") as mock_get:
        r_mock = MagicMock()
        r_mock.route_stream = AsyncMock(return_value=("groq", make_sse_gen()))
        mock_get.return_value = r_mock

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
            )

    assert r.headers.get("x-freeai-provider") == "groq"


@pytest.mark.asyncio
async def test_streaming_body_contains_data_events():
    with patch("routes.chat.get_router") as mock_get:
        r_mock = MagicMock()
        r_mock.route_stream = AsyncMock(return_value=("groq", make_sse_gen()))
        mock_get.return_value = r_mock

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
            )

    assert "data:" in r.text
    assert "[DONE]" in r.text


@pytest.mark.asyncio
async def test_streaming_503_when_all_providers_exhausted():
    with patch("routes.chat.get_router") as mock_get:
        r_mock = MagicMock()
        r_mock.route_stream = AsyncMock(
            side_effect=RuntimeError("All providers exhausted")
        )
        mock_get.return_value = r_mock

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
            )

    assert r.status_code == 503


@pytest.mark.asyncio
async def test_streaming_400_on_empty_messages():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/v1/chat/completions",
            json={"messages": [], "stream": True},
        )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# X-Provider header on non-streaming path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_streaming_has_x_provider_header():
    with patch("routes.chat.get_router") as mock_get:
        r_mock = MagicMock()
        r_mock.route = AsyncMock(return_value=mock_non_streaming_result())
        mock_get.return_value = r_mock

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

    assert r.status_code == 200
    assert r.headers.get("x-freeai-provider") == "groq"


@pytest.mark.asyncio
async def test_non_streaming_x_provider_matches_actual_provider():
    with patch("routes.chat.get_router") as mock_get:
        result = mock_non_streaming_result()
        # Change provider to cerebras to verify header reflects actual provider
        from dataclasses import replace

        result = replace(result, provider_name="cerebras")

        r_mock = MagicMock()
        r_mock.route = AsyncMock(return_value=result)
        mock_get.return_value = r_mock

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

    assert r.headers.get("x-freeai-provider") == "cerebras"


# ---------------------------------------------------------------------------
# Phase A v0.6.0 — _safe_stream guarantees [DONE] + error chunks
# Fix Premature close on AnythingLLM/LibreChat
# ---------------------------------------------------------------------------


async def _gen_no_done():
    """Provider that yields chunks but forgets the final [DONE] sentinel."""
    yield 'data: {"id":"c1","choices":[{"delta":{"content":"Hi"}}]}\n\n'
    yield 'data: {"id":"c1","choices":[{"delta":{"content":" there"}}]}\n\n'


async def _gen_with_done():
    """Provider that yields the canonical SSE termination."""
    yield 'data: {"id":"c1","choices":[{"delta":{"content":"Hi"}}]}\n\n'
    yield "data: [DONE]\n\n"


async def _gen_raise_at_open():
    """Provider that raises before yielding any chunk (e.g. 401 on raise_for_status)."""
    raise ProviderError("cerebras", status_code=401, reason="invalid api key")
    yield  # pragma: no cover


async def _gen_raise_mid_stream():
    """Provider that raises after yielding some content (e.g. timeout mid-stream)."""
    yield 'data: {"id":"c1","choices":[{"delta":{"content":"par"}}]}\n\n'
    raise ProviderError("groq", reason="network error: ReadTimeout")


@pytest.mark.asyncio
async def test_safe_stream_emits_done_when_provider_omits_it():
    """Wrapper must append [DONE] when the provider stream ends without it."""
    from services.router import _safe_stream

    chunks = [chunk async for chunk in _safe_stream("groq", _gen_no_done())]
    assert chunks[-1] == "data: [DONE]\n\n"
    assert any('"Hi"' in c for c in chunks)


@pytest.mark.asyncio
async def test_safe_stream_does_not_double_done_when_provider_emits_it():
    """Wrapper must not append a second [DONE] when the provider already sent one."""
    from services.router import _safe_stream

    chunks = [chunk async for chunk in _safe_stream("groq", _gen_with_done())]
    done_count = sum(1 for c in chunks if "[DONE]" in c)
    assert done_count == 1


@pytest.mark.asyncio
async def test_safe_stream_converts_provider_error_to_error_chunk():
    """Wrapper catches ProviderError raised before any chunk and yields an error + [DONE]."""
    from services.router import _safe_stream

    chunks = [chunk async for chunk in _safe_stream("cerebras", _gen_raise_at_open())]
    assert chunks[-1] == "data: [DONE]\n\n"
    error_chunk = next(c for c in chunks if '"error"' in c)
    payload = json.loads(error_chunk.removeprefix("data: ").strip())
    assert payload["error"]["provider"] == "cerebras"
    assert payload["error"]["code"] == 401


@pytest.mark.asyncio
async def test_safe_stream_converts_mid_stream_error_to_error_chunk():
    """Wrapper catches ProviderError mid-stream, keeps already-yielded chunks + appends error + [DONE]."""
    from services.router import _safe_stream

    chunks = [chunk async for chunk in _safe_stream("groq", _gen_raise_mid_stream())]
    assert chunks[-1] == "data: [DONE]\n\n"
    assert any('"par"' in c for c in chunks)
    assert any('"error"' in c for c in chunks)


@pytest.mark.asyncio
async def test_safe_stream_handles_unexpected_exception():
    """Wrapper catches any unexpected exception, converts to error chunk + [DONE] (never propagates)."""
    from services.router import _safe_stream

    async def _gen_unexpected():
        yield 'data: {"x":1}\n\n'
        raise ValueError("boom")

    chunks = [chunk async for chunk in _safe_stream("any", _gen_unexpected())]
    assert chunks[-1] == "data: [DONE]\n\n"
    assert any('"error"' in c for c in chunks)
