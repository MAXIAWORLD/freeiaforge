"""Tests TDD pour la route Anthropic-compatible /v1/messages — v0.4.0."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from core.models import ChatChoice, ChatResponse, ChatUsage, Message
from main import app
from providers.base import ProviderResult


def _mock_result(
    text: str = "Hello!",
    finish_reason: str = "stop",
    model: str = "llama-3.3-70b",
    prompt_tokens: int = 5,
    completion_tokens: int = 3,
) -> ProviderResult:
    return ProviderResult(
        response=ChatResponse(
            id="abc123",
            model=model,
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role="assistant", content=text),
                    finish_reason=finish_reason,
                )
            ],
            usage=ChatUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        ),
        provider_name="groq",
        tokens_used=prompt_tokens + completion_tokens,
    )


def _base_body(**kwargs) -> dict:
    return {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "Hello"}],
        **kwargs,
    }


# ---------------------------------------------------------------------------
# Response format
# ---------------------------------------------------------------------------


class TestAnthropicResponseFormat:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(return_value=_mock_result())
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post("/v1/messages", json=_base_body())
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_response_type_is_message(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(return_value=_mock_result())
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post("/v1/messages", json=_base_body())
        assert r.json()["type"] == "message"

    @pytest.mark.asyncio
    async def test_response_role_is_assistant(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(return_value=_mock_result())
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post("/v1/messages", json=_base_body())
        assert r.json()["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_content_is_list_of_text_blocks(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(return_value=_mock_result("Hi!"))
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post("/v1/messages", json=_base_body())
        content = r.json()["content"]
        assert isinstance(content, list)
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Hi!"

    @pytest.mark.asyncio
    async def test_id_prefixed_with_msg(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(return_value=_mock_result())
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post("/v1/messages", json=_base_body())
        assert r.json()["id"].startswith("msg_")

    @pytest.mark.asyncio
    async def test_usage_has_anthropic_keys(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(
                    return_value=_mock_result(prompt_tokens=10, completion_tokens=4)
                )
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post("/v1/messages", json=_base_body())
        usage = r.json()["usage"]
        assert usage["input_tokens"] == 10
        assert usage["output_tokens"] == 4


# ---------------------------------------------------------------------------
# stop_reason mapping
# ---------------------------------------------------------------------------


class TestStopReasonMapping:
    @pytest.mark.asyncio
    async def test_finish_reason_stop_maps_to_end_turn(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(return_value=_mock_result(finish_reason="stop"))
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post("/v1/messages", json=_base_body())
        assert r.json()["stop_reason"] == "end_turn"

    @pytest.mark.asyncio
    async def test_finish_reason_length_maps_to_max_tokens(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(return_value=_mock_result(finish_reason="length"))
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post("/v1/messages", json=_base_body())
        assert r.json()["stop_reason"] == "max_tokens"


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    @pytest.mark.asyncio
    async def test_system_prompt_included_in_route_call(self):
        captured: list = []

        async def fake_route(req):
            captured.append(req)
            return _mock_result()

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(route=fake_route)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                await c.post(
                    "/v1/messages",
                    json=_base_body(system="You are a pirate"),
                )
        req = captured[0]
        assert req.messages[0].role == "system"
        assert req.messages[0].content == "You are a pirate"

    @pytest.mark.asyncio
    async def test_no_system_prompt_no_system_message(self):
        captured: list = []

        async def fake_route(req):
            captured.append(req)
            return _mock_result()

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(route=fake_route)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                await c.post("/v1/messages", json=_base_body())
        req = captured[0]
        assert all(m.role != "system" for m in req.messages)


# ---------------------------------------------------------------------------
# Model hint routing
# ---------------------------------------------------------------------------


class TestModelHintRouting:
    @pytest.mark.asyncio
    async def test_known_provider_name_used_as_hint(self):
        captured: list = []

        async def fake_route(req):
            captured.append(req)
            return _mock_result()

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(route=fake_route)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                await c.post("/v1/messages", json=_base_body(model="groq"))
        assert captured[0].model == "groq"

    @pytest.mark.asyncio
    async def test_unknown_model_uses_auto(self):
        captured: list = []

        async def fake_route(req):
            captured.append(req)
            return _mock_result()

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(route=fake_route)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                await c.post(
                    "/v1/messages",
                    json=_base_body(model="claude-3-5-sonnet-20241022"),
                )
        assert captured[0].model == "auto"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_all_providers_exhausted_returns_529(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(side_effect=RuntimeError("All providers exhausted"))
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post("/v1/messages", json=_base_body())
        assert r.status_code == 529

    @pytest.mark.asyncio
    async def test_error_response_has_anthropic_format(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(side_effect=RuntimeError("All providers exhausted"))
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post("/v1/messages", json=_base_body())
        body = r.json()
        assert body["type"] == "error"
        assert "error" in body
        assert "message" in body["error"]

    @pytest.mark.asyncio
    async def test_stream_true_returns_400(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/v1/messages", json=_base_body(stream=True))
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_messages_returns_422(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post(
                "/v1/messages", json={"model": "claude-3", "max_tokens": 100}
            )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Headers compatibility
# ---------------------------------------------------------------------------


class TestHeadersCompatibility:
    @pytest.mark.asyncio
    async def test_accepts_x_api_key_header(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(return_value=_mock_result())
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post(
                    "/v1/messages",
                    json=_base_body(),
                    headers={"x-api-key": "sk-ant-anything"},
                )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_accepts_anthropic_version_header(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "routes.anthropic.get_router"
        ) as mock_get:
            mock_get.return_value = AsyncMock(
                route=AsyncMock(return_value=_mock_result())
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post(
                    "/v1/messages",
                    json=_base_body(),
                    headers={"anthropic-version": "2023-06-01"},
                )
        assert r.status_code == 200
