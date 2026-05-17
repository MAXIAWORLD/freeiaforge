"""
Tests intégration — simulation des clients réels.

Simule les payloads exacts envoyés par :
  - Cursor (OpenAI-compat, streaming)
  - Open WebUI (non-streaming + streaming)
  - LibreChat (stream + system prompt)
  - AnythingLLM (non-stream, model hint)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from core.models import (
    ChatChoice, ChatResponse, ChatUsage, Message,
)
from providers.base import ProviderResult


def _make_result(name: str = "groq") -> ProviderResult:
    return ProviderResult(
        response=ChatResponse(
            id="chatcmpl-abc123", model="llama-3.3-70b",
            choices=[ChatChoice(
                index=0,
                message=Message(role="assistant", content="Hello! How can I help?"),
                finish_reason="stop",
            )],
            usage=ChatUsage(prompt_tokens=10, completion_tokens=8, total_tokens=18),
        ),
        provider_name=name,
        tokens_used=18,
    )


def _mock_router(result=None):
    mock = AsyncMock()
    mock.route = AsyncMock(return_value=result or _make_result())
    mock.route_stream = AsyncMock(return_value=(
        "groq",
        _sse_gen(),
    ))
    return mock


async def _sse_gen():
    yield 'data: {"choices":[{"delta":{"content":"Hi"},"index":0}]}\n\n'
    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Cursor — stream=True, model="gpt-4o" (ignored, routed to best free)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cursor_streaming_request():
    """Cursor envoie stream=True avec son propre model name — doit retourner SSE."""
    from main import app

    with patch("routes.chat.get_router") as mock_get:
        mock_get.return_value = _mock_router()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "Hello"},
                    ],
                    "stream": True,
                    "temperature": 0.7,
                },
            )

    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_cursor_non_streaming_request():
    """Cursor en mode non-stream — retourne JSON standard."""
    from main import app

    with patch("routes.chat.get_router") as mock_get:
        mock_get.return_value = _mock_router()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "claude-3-5-sonnet",
                    "messages": [{"role": "user", "content": "Write a haiku"}],
                    "stream": False,
                    "max_tokens": 100,
                },
            )

    assert r.status_code == 200
    data = r.json()
    assert "choices" in data
    assert data["choices"][0]["message"]["role"] == "assistant"


# ---------------------------------------------------------------------------
# Open WebUI — model="freeai-gateway", non-stream
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_webui_non_streaming():
    """Open WebUI envoie model='freeai-gateway' — routé normalement."""
    from main import app

    with patch("routes.chat.get_router") as mock_get:
        mock_get.return_value = _mock_router()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "freeai-gateway",
                    "messages": [
                        {"role": "user", "content": "What is 2+2?"},
                    ],
                    "stream": False,
                },
            )

    assert r.status_code == 200
    assert r.json()["choices"][0]["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_open_webui_streaming():
    """Open WebUI streaming — SSE avec content-type correct."""
    from main import app

    with patch("routes.chat.get_router") as mock_get:
        mock_get.return_value = _mock_router()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "freeai-gateway",
                    "messages": [{"role": "user", "content": "Tell me a joke"}],
                    "stream": True,
                },
            )

    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# LibreChat — system prompt + history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_librechat_with_system_and_history():
    """LibreChat envoie system prompt + historique multi-tour."""
    from main import app

    with patch("routes.chat.get_router") as mock_get:
        mock_get.return_value = _mock_router()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "auto",
                    "messages": [
                        {"role": "system", "content": "You are a pirate."},
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Ahoy!"},
                        {"role": "user", "content": "Tell me a story"},
                    ],
                    "stream": False,
                    "temperature": 1.0,
                    "max_tokens": 512,
                },
            )

    assert r.status_code == 200


# ---------------------------------------------------------------------------
# AnythingLLM — model hint explicite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anythingllm_model_hint_groq():
    """AnythingLLM force le provider via model hint."""
    from main import app

    with patch("routes.chat.get_router") as mock_get:
        mock_get.return_value = _mock_router(_make_result("groq"))

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "groq",
                    "messages": [{"role": "user", "content": "Bonjour"}],
                    "stream": False,
                },
            )

    assert r.status_code == 200
    assert r.headers.get("x-freeai-provider") == "groq"


# ---------------------------------------------------------------------------
# Format de réponse OpenAI-compatible
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_response_has_openai_compatible_structure():
    """La réponse doit avoir tous les champs attendus par les clients OpenAI."""
    from main import app

    with patch("routes.chat.get_router") as mock_get:
        mock_get.return_value = _mock_router()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

    data = r.json()
    assert "id" in data
    assert "object" in data
    assert "choices" in data
    assert "usage" in data
    assert data["usage"]["total_tokens"] >= 0
    assert data["choices"][0]["message"]["role"] == "assistant"


@pytest.mark.asyncio
async def test_response_headers_present():
    """Headers X-FreeAI-Provider et X-FreeAI-Task doivent être présents."""
    from main import app

    with patch("routes.chat.get_router") as mock_get:
        mock_get.return_value = _mock_router()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )

    assert r.headers.get("x-freeai-provider") is not None
    assert r.headers.get("x-freeai-task") is not None


@pytest.mark.asyncio
async def test_empty_messages_returns_400():
    """Messages vide → 400 (tous les clients doivent gérer ça)."""
    from main import app

    with patch("routes.chat.get_router") as mock_get:
        mock_get.return_value = _mock_router()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": []},
            )

    assert r.status_code == 400
