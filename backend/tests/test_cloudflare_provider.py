"""
Tests TDD pour CloudflareProvider (Workers AI).

Cas couverts :
  - base_url contient account_id
  - attributs provider (name, priority)
  - complete() → endpoint correct avec account_id
  - complete() → Bearer token transmis
  - _select_best_model → préfère default, puis @cf/*/70b, puis premier
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from providers.cloudflare import CloudflareProvider
from core.models import ChatRequest, Message

ACCOUNT_ID = "test-account-abc123"
DEFAULT_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
FAKE_TOKEN = "cf-test-token-xyz"


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


def test_base_url_contains_account_id():
    p = CloudflareProvider(account_id=ACCOUNT_ID)
    assert ACCOUNT_ID in p.base_url


def test_base_url_points_to_cloudflare():
    p = CloudflareProvider(account_id=ACCOUNT_ID)
    assert "cloudflare.com" in p.base_url


def test_provider_name():
    assert CloudflareProvider(account_id=ACCOUNT_ID).name == "cloudflare"


def test_provider_default_model():
    assert CloudflareProvider(account_id=ACCOUNT_ID).default_model == DEFAULT_MODEL


def test_provider_priority_below_ollama():
    assert CloudflareProvider(account_id=ACCOUNT_ID).priority < 9


@pytest.mark.asyncio
async def test_complete_hits_endpoint_with_account_id():
    p = CloudflareProvider(account_id=ACCOUNT_ID)
    FakeClient, captured = _capture_payload()
    with patch("httpx.AsyncClient", FakeClient):
        await p.complete(_make_request(), FAKE_TOKEN)
    assert ACCOUNT_ID in captured["url"]
    assert "/chat/completions" in captured["url"]


@pytest.mark.asyncio
async def test_complete_sends_bearer_token():
    p = CloudflareProvider(account_id=ACCOUNT_ID)
    FakeClient, captured = _capture_payload()
    with patch("httpx.AsyncClient", FakeClient):
        await p.complete(_make_request(), FAKE_TOKEN)
    assert captured["headers"]["Authorization"] == f"Bearer {FAKE_TOKEN}"


def test_select_best_model_prefers_default():
    p = CloudflareProvider(account_id=ACCOUNT_ID)
    models = [DEFAULT_MODEL, "@cf/mistral/mistral-7b-instruct-v0.2"]
    assert p._select_best_model(models) == DEFAULT_MODEL


def test_select_best_model_prefers_cf_70b():
    p = CloudflareProvider(account_id=ACCOUNT_ID)
    models = ["@cf/mistral/mistral-7b", "@cf/meta/llama-3.1-70b-instruct", "@cf/other/model"]
    result = p._select_best_model(models)
    assert "70b" in result.lower()


def test_select_best_model_fallback_to_first():
    p = CloudflareProvider(account_id=ACCOUNT_ID)
    models = ["@cf/model-a", "@cf/model-b"]
    assert p._select_best_model(models) == "@cf/model-a"
