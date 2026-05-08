from __future__ import annotations

import httpx
import pytest

from providers.base import OpenAICompatibleProvider
from providers.cerebras import CerebrasProvider
from providers.gemini import GeminiProvider
from providers.groq import GroqProvider
from providers.huggingface import HuggingFaceProvider
from providers.mistral import MistralProvider
from providers.openrouter import OpenRouterProvider
from services.router import ProviderRouter
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Generic OpenAI-compatible discovery
# ---------------------------------------------------------------------------


class _DummyOpenAIProvider(OpenAICompatibleProvider):
    name = "dummy"
    priority = 99
    base_url = "https://api.dummy.example/v1"
    default_model = "dummy-default"

    async def complete(self, request, api_key):  # pragma: no cover — unused in tests
        raise NotImplementedError


def _mock_response(status: int, payload: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    if status >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=response
        )
    response.json.return_value = payload
    return response


def _mock_client(get_response):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=get_response)
    return client


@pytest.mark.asyncio
async def test_discover_returns_hardcoded_when_no_api_key():
    provider = _DummyOpenAIProvider()
    assert await provider.discover_default_model("") == "dummy-default"


@pytest.mark.asyncio
async def test_discover_keeps_default_when_listed():
    payload = {"data": [{"id": "dummy-default"}, {"id": "tiny"}]}
    with patch("httpx.AsyncClient", return_value=_mock_client(_mock_response(200, payload))):
        provider = _DummyOpenAIProvider()
        assert await provider.discover_default_model("key") == "dummy-default"


@pytest.mark.asyncio
async def test_discover_falls_back_to_first_when_default_gone():
    payload = {"data": [{"id": "tiny"}, {"id": "huge"}]}
    with patch("httpx.AsyncClient", return_value=_mock_client(_mock_response(200, payload))):
        provider = _DummyOpenAIProvider()
        assert await provider.discover_default_model("key") == "tiny"


@pytest.mark.asyncio
async def test_discover_falls_back_to_default_on_http_error():
    with patch("httpx.AsyncClient", return_value=_mock_client(_mock_response(500, {}))):
        provider = _DummyOpenAIProvider()
        assert await provider.discover_default_model("key") == "dummy-default"


@pytest.mark.asyncio
async def test_discover_falls_back_to_default_on_empty_response():
    with patch("httpx.AsyncClient", return_value=_mock_client(_mock_response(200, {"data": []}))):
        provider = _DummyOpenAIProvider()
        assert await provider.discover_default_model("key") == "dummy-default"


# ---------------------------------------------------------------------------
# Provider-specific heuristics
# ---------------------------------------------------------------------------


def test_cerebras_select_prefers_llama_70b_when_default_missing():
    provider = CerebrasProvider()
    models = ["qwen-3-32b", "llama-3.3-70b-instruct", "llama-3.1-8b"]
    assert provider._select_best_model(models) == "llama-3.3-70b-instruct"


def test_cerebras_select_keeps_default_when_listed():
    provider = CerebrasProvider()
    models = ["llama-3.3-70b", "llama-3.1-8b"]
    assert provider._select_best_model(models) == "llama-3.3-70b"


def test_groq_select_prefers_versatile():
    provider = GroqProvider()
    models = ["llama-3.1-8b-instant", "llama-3.1-70b-instruct", "mixtral-8x7b"]
    assert provider._select_best_model(models) == "llama-3.1-70b-instruct"


def test_mistral_select_prefers_latest_alias():
    provider = MistralProvider()
    models = ["mistral-large-2411", "mistral-large-latest", "mistral-small-latest"]
    assert provider._select_best_model(models) == "mistral-large-latest"


def test_mistral_select_falls_back_to_first_without_latest():
    provider = MistralProvider()
    models = ["mistral-large-2411", "mistral-medium-2503"]
    assert provider._select_best_model(models) == "mistral-large-2411"


def test_openrouter_filters_free_models():
    provider = OpenRouterProvider()
    models = [
        "anthropic/claude-3.5-sonnet",
        "meta-llama/llama-3.3-70b-instruct:free",
        "openai/gpt-4o",
    ]
    assert provider._select_best_model(models) == "meta-llama/llama-3.3-70b-instruct:free"


def test_openrouter_prefers_largest_free_llama():
    provider = OpenRouterProvider()
    models = [
        "meta-llama/llama-3.1-8b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "tinyllama/tinyllama-1.1b:free",
    ]
    assert provider._select_best_model(models) == "qwen/qwen-2.5-72b-instruct:free"


# ---------------------------------------------------------------------------
# Gemini (non-OpenAI listing endpoint)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_discover_uses_v1beta_models():
    payload = {
        "models": [
            {
                "name": "models/gemini-2.5-flash",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-2.0-flash",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/text-embedding-004",
                "supportedGenerationMethods": ["embedContent"],
            },
        ]
    }
    with patch("httpx.AsyncClient", return_value=_mock_client(_mock_response(200, payload))):
        provider = GeminiProvider()
        result = await provider.discover_default_model("key")
        assert result == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_gemini_keeps_default_when_listed():
    payload = {
        "models": [
            {
                "name": "models/gemini-1.5-flash",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-2.0-flash",
                "supportedGenerationMethods": ["generateContent"],
            },
        ]
    }
    with patch("httpx.AsyncClient", return_value=_mock_client(_mock_response(200, payload))):
        provider = GeminiProvider()
        assert await provider.discover_default_model("key") == "gemini-1.5-flash"


# ---------------------------------------------------------------------------
# HuggingFace skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_huggingface_skips_discovery():
    provider = HuggingFaceProvider()
    # Should NOT call any HTTP — patching to ensure no real network call occurs
    with patch("httpx.AsyncClient") as mock_client:
        result = await provider.discover_default_model("key")
        assert result == "meta-llama/Llama-3.1-70B-Instruct"
        mock_client.assert_not_called()


# ---------------------------------------------------------------------------
# ProviderRouter integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_refresh_updates_default_model():
    p = MagicMock()
    p.name = "cerebras"
    p.default_model = "llama-3.3-70b"
    p.discover_default_model = AsyncMock(return_value="llama-4-scout-17b-16e-instruct")

    router = ProviderRouter.__new__(ProviderRouter)
    router._providers = [p]
    router._api_keys = {"cerebras": "csk-x"}

    await router.refresh_default_models()

    assert p.default_model == "llama-4-scout-17b-16e-instruct"


@pytest.mark.asyncio
async def test_router_refresh_skips_provider_without_key():
    p = MagicMock()
    p.name = "cerebras"
    p.default_model = "llama-3.3-70b"
    p.discover_default_model = AsyncMock(return_value="should-not-be-used")

    router = ProviderRouter.__new__(ProviderRouter)
    router._providers = [p]
    router._api_keys = {}

    await router.refresh_default_models()

    assert p.default_model == "llama-3.3-70b"
    p.discover_default_model.assert_not_called()


@pytest.mark.asyncio
async def test_router_refresh_keeps_default_on_exception():
    p = MagicMock()
    p.name = "groq"
    p.default_model = "llama-3.3-70b-versatile"
    p.discover_default_model = AsyncMock(side_effect=RuntimeError("boom"))

    router = ProviderRouter.__new__(ProviderRouter)
    router._providers = [p]
    router._api_keys = {"groq": "gsk-x"}

    await router.refresh_default_models()

    assert p.default_model == "llama-3.3-70b-versatile"
