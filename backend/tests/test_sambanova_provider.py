"""
Tests TDD pour SambanovaProvider — sélection de modèle.

Cas couverts :
  - hint Llama-3.1-405B-Instruct  → transmis tel quel
  - hint Qwen2.5-72B-Instruct     → transmis tel quel
  - model == "auto"               → default_model (70B)
  - model == "freeai-gateway"     → default_model (70B)
  - model inconnu                 → default_model (70B)
  - model == default_model (70B)  → transmis tel quel (identité)
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from providers.sambanova import SambanovaProvider
from core.models import ChatRequest, Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "Meta-Llama-3.3-70B-Instruct"
MODEL_405B = "Llama-3.1-405B-Instruct"
MODEL_QWEN = "Qwen2.5-72B-Instruct"

FAKE_API_KEY = "test-key"


def _make_request(model: str = "auto") -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=[Message(role="user", content="ping")],
    )


def _fake_httpx_response(model_used: str) -> MagicMock:
    """Simule une réponse HTTP 200 OpenAI-compatible."""
    body = {
        "id": "test-id",
        "model": model_used,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "pong"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 3,
            "total_tokens": 8,
        },
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = body
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _capture_payload(response_model: str):
    """
    Context manager factory : intercepte l'appel httpx.AsyncClient.post
    et retourne le payload JSON envoyé.
    """
    captured: dict = {}

    class _FakeClient:
        def __init__(self, **kwargs):
            pass  # absorbe timeout= et tout autre kwarg

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def post(self, url, *, headers, json, **kwargs):
            captured["json"] = json
            return _fake_httpx_response(response_model)

    return _FakeClient, captured


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_hint_405b_is_forwarded():
    """Un hint Llama-3.1-405B-Instruct doit être transmis au provider."""
    provider = SambanovaProvider()
    FakeClient, captured = _capture_payload(MODEL_405B)

    with patch("httpx.AsyncClient", FakeClient):
        await provider.complete(_make_request(MODEL_405B), FAKE_API_KEY)

    assert captured["json"]["model"] == MODEL_405B


@pytest.mark.asyncio
async def test_model_hint_qwen_is_forwarded():
    """Un hint Qwen2.5-72B-Instruct doit être transmis au provider."""
    provider = SambanovaProvider()
    FakeClient, captured = _capture_payload(MODEL_QWEN)

    with patch("httpx.AsyncClient", FakeClient):
        await provider.complete(_make_request(MODEL_QWEN), FAKE_API_KEY)

    assert captured["json"]["model"] == MODEL_QWEN


@pytest.mark.asyncio
async def test_model_auto_uses_default():
    """model='auto' → default_model (70B)."""
    provider = SambanovaProvider()
    FakeClient, captured = _capture_payload(DEFAULT_MODEL)

    with patch("httpx.AsyncClient", FakeClient):
        await provider.complete(_make_request("auto"), FAKE_API_KEY)

    assert captured["json"]["model"] == DEFAULT_MODEL


@pytest.mark.asyncio
async def test_model_freeai_gateway_uses_default():
    """model='freeai-gateway' → default_model (70B)."""
    provider = SambanovaProvider()
    FakeClient, captured = _capture_payload(DEFAULT_MODEL)

    with patch("httpx.AsyncClient", FakeClient):
        await provider.complete(_make_request("freeai-gateway"), FAKE_API_KEY)

    assert captured["json"]["model"] == DEFAULT_MODEL


@pytest.mark.asyncio
async def test_model_freeaigate_alias_uses_default():
    """model='freeaigate' (rebrand v0.6.0) → default_model. Backward-compat: 'freeai-gateway' kept."""
    provider = SambanovaProvider()
    FakeClient, captured = _capture_payload(DEFAULT_MODEL)

    with patch("httpx.AsyncClient", FakeClient):
        await provider.complete(_make_request("freeaigate"), FAKE_API_KEY)

    assert captured["json"]["model"] == DEFAULT_MODEL


@pytest.mark.asyncio
async def test_unknown_model_uses_default():
    """Tout modèle non reconnu → default_model (70B)."""
    provider = SambanovaProvider()
    FakeClient, captured = _capture_payload(DEFAULT_MODEL)

    with patch("httpx.AsyncClient", FakeClient):
        await provider.complete(_make_request("gpt-99-turbo"), FAKE_API_KEY)

    assert captured["json"]["model"] == DEFAULT_MODEL


@pytest.mark.asyncio
async def test_model_default_70b_is_identity():
    """Spécifier explicitement le 70B → transmis tel quel."""
    provider = SambanovaProvider()
    FakeClient, captured = _capture_payload(DEFAULT_MODEL)

    with patch("httpx.AsyncClient", FakeClient):
        await provider.complete(_make_request(DEFAULT_MODEL), FAKE_API_KEY)

    assert captured["json"]["model"] == DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Vérification de la liste des modèles supportés
# ---------------------------------------------------------------------------


def test_supported_models_constant():
    """SUPPORTED_MODELS doit contenir exactement les 3 modèles."""
    provider = SambanovaProvider()
    assert hasattr(provider, "SUPPORTED_MODELS"), "SUPPORTED_MODELS manquant"
    assert MODEL_405B in provider.SUPPORTED_MODELS
    assert MODEL_QWEN in provider.SUPPORTED_MODELS
    assert DEFAULT_MODEL in provider.SUPPORTED_MODELS
    assert len(provider.SUPPORTED_MODELS) == 3
