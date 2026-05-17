"""
Tests TDD — routing Phase 2 par type de tâche.

Cas couverts :
  - long_context → seul Gemini tenté
  - long_context sans Gemini → fallback tous providers
  - vision → Gemini + OpenRouter seulement
  - code → Groq/Cerebras en priorité
  - default → quota routing standard
  - X-FreeAI-Task header dans la réponse HTTP
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import httpx
from fastapi.testclient import TestClient

from core.models import (
    ChatChoice, ChatRequest, ChatResponse, ChatUsage, Message, ProviderStatus
)
from providers.base import ProviderResult
from services.router import ProviderRouter
from services.task_inference import LONG_CONTEXT_CHAR_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(name: str) -> ProviderResult:
    return ProviderResult(
        response=ChatResponse(
            id="x", model="m",
            choices=[ChatChoice(index=0, message=Message(role="assistant", content="ok"), finish_reason="stop")],
            usage=ChatUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
        provider_name=name,
        tokens_used=2,
    )


def _mock_quota_ok() -> AsyncMock:
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    async def _status(name: str) -> ProviderStatus:
        return ProviderStatus(
            name=name, available=True,
            requests_used=0, requests_limit=1000,
            tokens_used=0, tokens_limit=1_000_000,
        )
    quota.get_status = AsyncMock(side_effect=_status)
    return quota


def _image_request() -> ChatRequest:
    return ChatRequest(
        messages=[Message(
            role="user",
            content=[
                {"type": "text", "text": "Describe this"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        )]
    )


def _long_request() -> ChatRequest:
    big = "x " * (LONG_CONTEXT_CHAR_THRESHOLD + 100)
    return ChatRequest(messages=[Message(role="user", content=big)])


def _code_request() -> ChatRequest:
    return ChatRequest(
        messages=[Message(role="user", content="fix this:\n```python\ndef foo(): pass\n```")]
    )


def _default_request() -> ChatRequest:
    return ChatRequest(messages=[Message(role="user", content="bonjour")])


def _router_with(*names: str) -> tuple[ProviderRouter, dict[str, AsyncMock]]:
    providers = []
    mocks = {}
    for i, name in enumerate(names):
        p = AsyncMock()
        p.name = name
        p.priority = i + 1
        p.complete = AsyncMock(return_value=_make_result(name))
        providers.append(p)
        mocks[name] = p
    router = ProviderRouter(
        providers=providers,
        quota=_mock_quota_ok(),
        api_keys={n: "key" for n in names},
    )
    return router, mocks


# ---------------------------------------------------------------------------
# long_context → Gemini seul
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_long_context_routes_to_gemini_only():
    router, mocks = _router_with("cerebras", "groq", "gemini")
    result = await router.route(_long_request())
    assert result.provider_name == "gemini"
    mocks["cerebras"].complete.assert_not_called()
    mocks["groq"].complete.assert_not_called()


@pytest.mark.asyncio
async def test_long_context_fallback_if_no_gemini():
    """Sans Gemini configuré, fallback sur tous les providers."""
    router, mocks = _router_with("cerebras", "groq")
    result = await router.route(_long_request())
    # cerebras est skippé (char limit), groq sert
    assert result.provider_name == "groq"


# ---------------------------------------------------------------------------
# vision → Gemini + OpenRouter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vision_routes_to_gemini():
    router, mocks = _router_with("cerebras", "groq", "gemini")
    result = await router.route(_image_request())
    assert result.provider_name == "gemini"
    mocks["cerebras"].complete.assert_not_called()
    mocks["groq"].complete.assert_not_called()


@pytest.mark.asyncio
async def test_vision_allows_openrouter():
    """Vision sans Gemini → OpenRouter doit être tenté."""
    router, mocks = _router_with("cerebras", "groq", "openrouter")
    result = await router.route(_image_request())
    assert result.provider_name == "openrouter"
    mocks["cerebras"].complete.assert_not_called()
    mocks["groq"].complete.assert_not_called()


# ---------------------------------------------------------------------------
# code → Groq/Cerebras prioritaires
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_code_prefers_groq_over_others():
    """Pour une requête code, Groq doit être tenté avant Gemini même si Gemini est en premier."""
    router, mocks = _router_with("gemini", "openrouter", "groq")
    result = await router.route(_code_request())
    assert result.provider_name in ("groq", "cerebras")
    # gemini ne doit pas avoir été appelé (groq a servi en premier)
    mocks["gemini"].complete.assert_not_called()


@pytest.mark.asyncio
async def test_code_prefers_cerebras_or_groq():
    router, mocks = _router_with("cerebras", "gemini")
    result = await router.route(_code_request())
    assert result.provider_name == "cerebras"


# ---------------------------------------------------------------------------
# default → quota routing standard (vérifié via test quota sort)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_default_uses_first_available_provider():
    router, mocks = _router_with("cerebras", "groq")
    result = await router.route(_default_request())
    assert result.provider_name in ("cerebras", "groq")


# ---------------------------------------------------------------------------
# X-FreeAI-Task header dans la réponse HTTP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_response_has_x_freeai_task_header_code():
    """La réponse HTTP doit contenir X-FreeAI-Task pour une requête code."""
    from main import app

    with patch("routes.chat.get_router") as mock_get:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_make_result("groq"))
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "fix this:\n```python\npass\n```"}]},
            )

    assert r.status_code == 200
    assert r.headers.get("x-freeai-task") == "code"


@pytest.mark.asyncio
async def test_http_response_has_x_freeai_task_header_default():
    """Requête normale → X-FreeAI-Task: default."""
    from main import app

    with patch("routes.chat.get_router") as mock_get:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_make_result("groq"))
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "bonjour"}]},
            )

    assert r.status_code == 200
    assert r.headers.get("x-freeai-task") == "default"
