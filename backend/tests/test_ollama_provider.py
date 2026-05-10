"""Tests TDD pour OllamaProvider — freeaigate v0.3.0."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.models import ChatRequest, Message


def _make_openai_response(model: str = "llama3.2") -> dict:
    return {
        "id": "ollama-test-123",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from Ollama"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
    }


def _make_request() -> ChatRequest:
    return ChatRequest(messages=[Message(role="user", content="Hello")])


def _fake_post(response_data: dict):
    async def _post(url, *, headers, json, **kwargs):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = response_data
        return mock_resp

    return _post


def _mock_client(post_fn):
    mock_client = AsyncMock()
    mock_client.post = post_fn
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestOllamaProviderAttributes:
    def test_name_is_ollama(self):
        from providers.ollama import OllamaProvider

        assert OllamaProvider().name == "ollama"

    def test_priority_is_9(self):
        from providers.ollama import OllamaProvider

        assert OllamaProvider().priority == 9

    def test_default_model_is_llama32(self):
        from providers.ollama import OllamaProvider

        assert OllamaProvider().default_model == "llama3.2"

    def test_custom_model_via_init(self):
        from providers.ollama import OllamaProvider

        p = OllamaProvider(model="mistral:7b")
        assert p.default_model == "mistral:7b"

    def test_default_base_url_contains_localhost(self):
        from providers.ollama import OllamaProvider

        assert "localhost:11434" in OllamaProvider().base_url

    def test_custom_base_url_via_init(self):
        from providers.ollama import OllamaProvider

        p = OllamaProvider(base_url="http://192.168.1.100:11434")
        assert "192.168.1.100:11434" in p.base_url

    def test_base_url_includes_v1(self):
        from providers.ollama import OllamaProvider

        p = OllamaProvider(base_url="http://localhost:11434")
        assert p.base_url.endswith("/v1")

    def test_trailing_slash_in_base_url_stripped(self):
        from providers.ollama import OllamaProvider

        p = OllamaProvider(base_url="http://localhost:11434/")
        assert not p.base_url.endswith("//v1")
        assert p.base_url.endswith("/v1")


class TestOllamaComplete:
    @pytest.mark.asyncio
    async def test_complete_success_returns_provider_result(self):
        from providers.ollama import OllamaProvider

        provider = OllamaProvider()
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_client(_fake_post(_make_openai_response()))
            result = await provider.complete(_make_request(), api_key="local")

        assert result.provider_name == "ollama"
        assert result.tokens_used == 14
        assert result.response.choices[0].message.content == "Hello from Ollama"

    @pytest.mark.asyncio
    async def test_posts_to_correct_endpoint(self):
        from providers.ollama import OllamaProvider

        captured_urls: list[str] = []

        async def fake_post(url, *, headers, json, **kwargs):
            captured_urls.append(url)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = _make_openai_response()
            return mock_resp

        provider = OllamaProvider(base_url="http://localhost:11434")
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_client(fake_post)
            await provider.complete(_make_request(), api_key="local")

        assert captured_urls == ["http://localhost:11434/v1/chat/completions"]

    @pytest.mark.asyncio
    async def test_uses_configured_model_in_payload(self):
        from providers.ollama import OllamaProvider

        captured_json: dict = {}

        async def fake_post(url, *, headers, json, **kwargs):
            captured_json.update(json)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = _make_openai_response("phi4-mini")
            return mock_resp

        provider = OllamaProvider(model="phi4-mini")
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_client(fake_post)
            await provider.complete(_make_request(), api_key="local")

        assert captured_json["model"] == "phi4-mini"

    @pytest.mark.asyncio
    async def test_http_error_raises_provider_error(self):
        from providers.base import ProviderError
        from providers.ollama import OllamaProvider

        async def fake_post(url, *, headers, json, **kwargs):
            request = httpx.Request("POST", url)
            response = httpx.Response(500, request=request)
            raise httpx.HTTPStatusError(
                "server error", request=request, response=response
            )

        provider = OllamaProvider()
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_client(fake_post)
            with pytest.raises(ProviderError) as exc_info:
                await provider.complete(_make_request(), api_key="local")

        assert exc_info.value.provider == "ollama"
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_connect_error_raises_provider_error_immediately(self):
        """ConnectError (Ollama not running) must raise ProviderError, not hang."""
        from providers.base import ProviderError
        from providers.ollama import OllamaProvider

        async def fake_post(url, *, headers, json, **kwargs):
            raise httpx.ConnectError("connection refused")

        provider = OllamaProvider()
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_client(fake_post)
            with pytest.raises(ProviderError) as exc_info:
                await provider.complete(_make_request(), api_key="local")

        assert exc_info.value.provider == "ollama"
        assert "network error" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_malformed_response_raises_provider_error(self):
        from providers.base import ProviderError
        from providers.ollama import OllamaProvider

        provider = OllamaProvider()
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_client(_fake_post({"broken": True}))
            with pytest.raises(ProviderError) as exc_info:
                await provider.complete(_make_request(), api_key="local")

        assert exc_info.value.provider == "ollama"
        assert exc_info.value.reason == "malformed response"
