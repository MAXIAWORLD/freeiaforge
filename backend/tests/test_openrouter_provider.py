"""Tests TDD pour OpenRouterProvider — Phase 2 FreeIA Gateway v0.2.0."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.models import ChatRequest, Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_openai_response(model: str = "openrouter/free") -> dict:
    """Fake payload returned by OpenRouter's /chat/completions."""
    return {
        "id": "or-test-123",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from OpenRouter"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _make_request() -> ChatRequest:
    return ChatRequest(
        messages=[Message(role="user", content="Hello")],
        temperature=0.7,
    )


# ---------------------------------------------------------------------------
# Unit tests — provider attributes
# ---------------------------------------------------------------------------


class TestOpenRouterProviderAttributes:
    def test_name_is_openrouter(self):
        from providers.openrouter import OpenRouterProvider

        p = OpenRouterProvider()
        assert p.name == "openrouter"

    def test_base_url(self):
        from providers.openrouter import OpenRouterProvider

        p = OpenRouterProvider()
        assert p.base_url == "https://openrouter.ai/api/v1"

    def test_default_model(self):
        from providers.openrouter import OpenRouterProvider

        p = OpenRouterProvider()
        assert p.default_model == "meta-llama/llama-3.3-70b-instruct:free"

    def test_priority_is_7(self):
        from providers.openrouter import OpenRouterProvider

        p = OpenRouterProvider()
        assert p.priority == 7

    def test_priority_is_lowest_among_providers(self):
        """Priority 7 = last resort fallback."""
        from providers.cerebras import CerebrasProvider
        from providers.mistral import MistralProvider
        from providers.openrouter import OpenRouterProvider

        or_p = OpenRouterProvider()
        assert or_p.priority > CerebrasProvider().priority
        assert or_p.priority > MistralProvider().priority


# ---------------------------------------------------------------------------
# Unit tests — custom headers
# ---------------------------------------------------------------------------


class TestOpenRouterCustomHeaders:
    @pytest.mark.asyncio
    async def test_http_referer_header_sent(self):
        """HTTP-Referer must be present in the request sent to OpenRouter."""
        from providers.openrouter import OpenRouterProvider

        captured_headers: dict = {}

        async def fake_post(url, *, headers, json, **kwargs):
            captured_headers.update(headers)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = _make_openai_response()
            return mock_resp

        provider = OpenRouterProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = fake_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await provider.complete(_make_request(), api_key="test-key")

        assert "HTTP-Referer" in captured_headers
        assert captured_headers["HTTP-Referer"] == "https://maxiaworld.app"

    @pytest.mark.asyncio
    async def test_x_title_header_sent(self):
        """X-Title must be present in the request sent to OpenRouter."""
        from providers.openrouter import OpenRouterProvider

        captured_headers: dict = {}

        async def fake_post(url, *, headers, json, **kwargs):
            captured_headers.update(headers)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = _make_openai_response()
            return mock_resp

        provider = OpenRouterProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = fake_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await provider.complete(_make_request(), api_key="test-key")

        assert "X-Title" in captured_headers
        assert captured_headers["X-Title"] == "FreeIA Gateway"

    @pytest.mark.asyncio
    async def test_authorization_header_still_present(self):
        """Authorization Bearer must remain even with custom headers."""
        from providers.openrouter import OpenRouterProvider

        captured_headers: dict = {}

        async def fake_post(url, *, headers, json, **kwargs):
            captured_headers.update(headers)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = _make_openai_response()
            return mock_resp

        provider = OpenRouterProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = fake_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await provider.complete(_make_request(), api_key="sk-or-test")

        assert "Authorization" in captured_headers
        assert captured_headers["Authorization"] == "Bearer sk-or-test"

    @pytest.mark.asyncio
    async def test_correct_endpoint_called(self):
        """Must POST to https://openrouter.ai/api/v1/chat/completions."""
        from providers.openrouter import OpenRouterProvider

        captured_url: list[str] = []

        async def fake_post(url, *, headers, json, **kwargs):
            captured_url.append(url)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = _make_openai_response()
            return mock_resp

        provider = OpenRouterProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = fake_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await provider.complete(_make_request(), api_key="test-key")

        assert captured_url == ["https://openrouter.ai/api/v1/chat/completions"]


# ---------------------------------------------------------------------------
# Unit tests — error handling (inherited behaviour)
# ---------------------------------------------------------------------------


class TestOpenRouterErrorHandling:
    @pytest.mark.asyncio
    async def test_http_error_raises_provider_error(self):
        from providers.base import ProviderError
        from providers.openrouter import OpenRouterProvider

        provider = OpenRouterProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()

            async def fake_post(url, *, headers, json, **kwargs):
                request = httpx.Request("POST", url)
                response = httpx.Response(429, request=request)
                raise httpx.HTTPStatusError(
                    "rate limited", request=request, response=response
                )

            mock_client.post = fake_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ProviderError) as exc_info:
                await provider.complete(_make_request(), api_key="test-key")

        assert exc_info.value.provider == "openrouter"
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_network_error_raises_provider_error(self):
        from providers.base import ProviderError
        from providers.openrouter import OpenRouterProvider

        provider = OpenRouterProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()

            async def fake_post(url, *, headers, json, **kwargs):
                raise httpx.ConnectError("connection refused")

            mock_client.post = fake_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ProviderError) as exc_info:
                await provider.complete(_make_request(), api_key="test-key")

        assert exc_info.value.provider == "openrouter"
        assert "network error" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_malformed_response_raises_provider_error(self):
        from providers.base import ProviderError
        from providers.openrouter import OpenRouterProvider

        provider = OpenRouterProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()

            async def fake_post(url, *, headers, json, **kwargs):
                mock_resp = MagicMock()
                mock_resp.raise_for_status = MagicMock()
                mock_resp.json.return_value = {"broken": "response"}
                return mock_resp

            mock_client.post = fake_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ProviderError) as exc_info:
                await provider.complete(_make_request(), api_key="test-key")

        assert exc_info.value.provider == "openrouter"
        assert exc_info.value.reason == "malformed response"


# ---------------------------------------------------------------------------
# Integration — result shape
# ---------------------------------------------------------------------------


class TestOpenRouterResult:
    @pytest.mark.asyncio
    async def test_returns_provider_result_with_correct_provider_name(self):
        from providers.openrouter import OpenRouterProvider

        provider = OpenRouterProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()

            async def fake_post(url, *, headers, json, **kwargs):
                mock_resp = MagicMock()
                mock_resp.raise_for_status = MagicMock()
                mock_resp.json.return_value = _make_openai_response()
                return mock_resp

            mock_client.post = fake_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await provider.complete(_make_request(), api_key="test-key")

        assert result.provider_name == "openrouter"
        assert result.tokens_used == 15

    @pytest.mark.asyncio
    async def test_returns_correct_message_content(self):
        from providers.openrouter import OpenRouterProvider

        provider = OpenRouterProvider()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()

            async def fake_post(url, *, headers, json, **kwargs):
                mock_resp = MagicMock()
                mock_resp.raise_for_status = MagicMock()
                mock_resp.json.return_value = _make_openai_response()
                return mock_resp

            mock_client.post = fake_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await provider.complete(_make_request(), api_key="test-key")

        assert result.response.choices[0].message.content == "Hello from OpenRouter"
