"""
Tests TDD pour NvidiaProvider (NVIDIA NIM).

Cas couverts :
  - attributs provider (name, base_url, priority)
  - complete() → endpoint correct
  - complete() → Bearer token transmis
  - complete() → default_model si model inconnu / auto
  - _select_best_model → préfère default, puis 70b, puis premier
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from providers.nvidia_nim import NvidiaProvider
from core.models import ChatRequest, Message

DEFAULT_MODEL = "meta/llama-3.3-70b-instruct"
FAKE_KEY = "nvapi-test-key"


def _make_request(model: str = DEFAULT_MODEL) -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=[Message(role="user", content="ping")],
    )


def _fake_response(model_used: str) -> MagicMock:
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
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = body
    mock.raise_for_status = MagicMock()
    return mock


def _capture_payload():
    captured: dict = {}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def post(self, url, *, headers, json, **kwargs):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _fake_response(json.get("model", DEFAULT_MODEL))

    return FakeClient, captured


def test_provider_name():
    assert NvidiaProvider().name == "nvidia_nim"


def test_provider_base_url_points_to_nim():
    p = NvidiaProvider()
    assert "integrate.api.nvidia.com" in p.base_url


def test_provider_default_model():
    assert NvidiaProvider().default_model == DEFAULT_MODEL


def test_provider_priority_below_ollama():
    assert NvidiaProvider().priority < 9  # Ollama = 9


@pytest.mark.asyncio
async def test_complete_hits_correct_endpoint():
    p = NvidiaProvider()
    FakeClient, captured = _capture_payload()
    with patch("httpx.AsyncClient", FakeClient):
        await p.complete(_make_request(), FAKE_KEY)
    assert "integrate.api.nvidia.com" in captured["url"]
    assert "/v1/chat/completions" in captured["url"]


@pytest.mark.asyncio
async def test_complete_sends_bearer_token():
    p = NvidiaProvider()
    FakeClient, captured = _capture_payload()
    with patch("httpx.AsyncClient", FakeClient):
        await p.complete(_make_request(), FAKE_KEY)
    assert captured["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"


@pytest.mark.asyncio
async def test_complete_auto_uses_default_model():
    p = NvidiaProvider()
    FakeClient, captured = _capture_payload()
    with patch("httpx.AsyncClient", FakeClient):
        await p.complete(_make_request("auto"), FAKE_KEY)
    assert captured["json"]["model"] == DEFAULT_MODEL


def test_select_best_model_prefers_default():
    p = NvidiaProvider()
    models = ["nvidia/llama-3.1-nemotron-70b", DEFAULT_MODEL, "meta/llama-3.1-8b"]
    assert p._select_best_model(models) == DEFAULT_MODEL


def test_select_best_model_prefers_llama_70b():
    p = NvidiaProvider()
    models = ["meta/llama-3.1-8b-instruct", "meta/llama-3.3-70b-instruct-v2", "other/model"]
    result = p._select_best_model(models)
    assert "70b" in result.lower()


def test_select_best_model_fallback_to_first():
    p = NvidiaProvider()
    models = ["some/model-8b", "another/model-7b"]
    assert p._select_best_model(models) == "some/model-8b"
