"""
TDD — P1 streaming SSE + P2 X-Provider header (v0.5.0)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from main import app
from core.models import ChatResponse, ChatChoice, ChatUsage, Message
from providers.base import ProviderResult


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

    assert r.headers.get("x-provider") == "groq"


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
    assert r.headers.get("x-provider") == "groq"


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

    assert r.headers.get("x-provider") == "cerebras"
