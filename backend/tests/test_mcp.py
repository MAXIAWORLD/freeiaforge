from __future__ import annotations

import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from core.models import ChatResponse, ChatChoice, ChatUsage, Message, ProviderStatus
from providers.base import ProviderResult


def mock_result() -> ProviderResult:
    return ProviderResult(
        response=ChatResponse(
            id="mcp-test-123",
            model="llama-3.3-70b",
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role="assistant", content="MCP response text"),
                    finish_reason="stop",
                )
            ],
            usage=ChatUsage(prompt_tokens=5, completion_tokens=4, total_tokens=9),
        ),
        provider_name="groq",
        tokens_used=9,
    )


def mock_statuses() -> list[ProviderStatus]:
    return [
        ProviderStatus(
            name="groq",
            available=True,
            requests_used=10,
            requests_limit=100,
            tokens_used=500,
            tokens_limit=10000,
        ),
        ProviderStatus(
            name="cerebras",
            available=False,
            requests_used=100,
            requests_limit=100,
            tokens_used=9999,
            tokens_limit=10000,
            last_error="quota exceeded",
        ),
    ]


# ---------------------------------------------------------------------------
# GET /mcp — manifest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_manifest_returns_200():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/mcp")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_mcp_manifest_contains_name():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/mcp")
    data = r.json()
    assert data["name"] == "freeai-gateway"


@pytest.mark.asyncio
async def test_mcp_manifest_has_two_tools():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/mcp")
    data = r.json()
    assert "tools" in data
    assert len(data["tools"]) == 2


@pytest.mark.asyncio
async def test_mcp_manifest_tools_names():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/mcp")
    tools = r.json()["tools"]
    assert tools[0]["name"] == "chat"
    assert tools[1]["name"] == "providers_status"


@pytest.mark.asyncio
async def test_mcp_manifest_version():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/mcp")
    assert r.json()["version"] == "0.2.0"


# ---------------------------------------------------------------------------
# POST /mcp/tools/chat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_chat_returns_200():
    with patch("routes.mcp.get_router") as mock_get:
        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=mock_result())
        mock_get.return_value = mock_router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/mcp/tools/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_mcp_chat_content_type_is_text():
    with patch("routes.mcp.get_router") as mock_get:
        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=mock_result())
        mock_get.return_value = mock_router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/mcp/tools/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    data = r.json()
    assert data["content"][0]["type"] == "text"


@pytest.mark.asyncio
async def test_mcp_chat_text_is_assistant_reply():
    with patch("routes.mcp.get_router") as mock_get:
        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=mock_result())
        mock_get.return_value = mock_router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/mcp/tools/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    data = r.json()
    assert data["content"][0]["text"] == "MCP response text"


@pytest.mark.asyncio
async def test_mcp_chat_without_messages_returns_422():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post("/mcp/tools/chat", json={})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_mcp_chat_model_hint_forwarded():
    """Le champ model est bien passé au ChatRequest sous-jacent."""
    with patch("routes.mcp.get_router") as mock_get:
        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=mock_result())
        mock_get.return_value = mock_router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post(
                "/mcp/tools/chat",
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "model": "groq",
                },
            )

    call_args = mock_router.route.call_args[0][0]
    assert call_args.model == "groq"


# ---------------------------------------------------------------------------
# POST /mcp/tools/providers_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_providers_status_returns_200():
    with patch("routes.mcp.get_router") as mock_get:
        mock_router = MagicMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=mock_statuses())
        mock_get.return_value = mock_router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/mcp/tools/providers_status", json={})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_mcp_providers_status_content_is_valid_json():
    with patch("routes.mcp.get_router") as mock_get:
        mock_router = MagicMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=mock_statuses())
        mock_get.return_value = mock_router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/mcp/tools/providers_status", json={})

    data = r.json()
    text = data["content"][0]["text"]
    parsed = json.loads(text)
    assert isinstance(parsed, list)
    assert parsed[0]["name"] == "groq"
