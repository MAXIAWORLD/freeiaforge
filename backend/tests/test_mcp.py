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
# GET /mcp — manifest legacy
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
    assert r.json()["name"] == "freeai-gateway"


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
async def test_mcp_manifest_updated_description():
    """'6+ free LLMs' et '7 providers' remplacés par les valeurs exactes."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/mcp")
    data = r.json()
    assert "10 LLMs" in data["description"]
    chat_tool = next(t for t in data["tools"] if t["name"] == "chat")
    assert "9 cloud" in chat_tool["description"]


@pytest.mark.asyncio
async def test_mcp_manifest_model_hint_includes_nvidia_and_cloudflare():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/mcp")
    chat_tool = next(t for t in r.json()["tools"] if t["name"] == "chat")
    model_desc = chat_tool["inputSchema"]["properties"]["model"]["description"]
    assert "nvidia_nim" in model_desc
    assert "cloudflare" in model_desc


# ---------------------------------------------------------------------------
# POST /mcp — JSON-RPC 2.0 initialize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jsonrpc_initialize_returns_200():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1},
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_jsonrpc_initialize_envelope():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1},
        )
    data = r.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert "result" in data
    assert "error" not in data


@pytest.mark.asyncio
async def test_jsonrpc_initialize_protocol_version():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 5},
        )
    assert r.json()["result"]["protocolVersion"] == "2025-03-26"


@pytest.mark.asyncio
async def test_jsonrpc_initialize_server_info():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 2},
        )
    result = r.json()["result"]
    assert result["serverInfo"]["name"] == "freeai-gateway"
    assert "capabilities" in result


# ---------------------------------------------------------------------------
# POST /mcp — JSON-RPC 2.0 tools/list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jsonrpc_tools_list_envelope():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 2},
        )
    data = r.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 2
    assert "result" in data


@pytest.mark.asyncio
async def test_jsonrpc_tools_list_two_tools():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 3},
        )
    tools = r.json()["result"]["tools"]
    assert len(tools) == 2
    assert tools[0]["name"] == "chat"
    assert tools[1]["name"] == "providers_status"


@pytest.mark.asyncio
async def test_jsonrpc_tools_list_has_input_schema():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 4},
        )
    for tool in r.json()["result"]["tools"]:
        assert "inputSchema" in tool


# ---------------------------------------------------------------------------
# POST /mcp — JSON-RPC 2.0 tools/call chat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jsonrpc_tools_call_chat_result():
    with patch("routes.mcp.get_router") as mock_get:
        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=mock_result())
        mock_get.return_value = mock_router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "chat",
                        "arguments": {"messages": [{"role": "user", "content": "hello"}]},
                    },
                    "id": 3,
                },
            )
    data = r.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 3
    assert data["result"]["content"][0]["type"] == "text"
    assert data["result"]["content"][0]["text"] == "MCP response text"


@pytest.mark.asyncio
async def test_jsonrpc_tools_call_chat_model_hint():
    with patch("routes.mcp.get_router") as mock_get:
        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=mock_result())
        mock_get.return_value = mock_router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "chat",
                        "arguments": {
                            "messages": [{"role": "user", "content": "hi"}],
                            "model": "groq",
                        },
                    },
                    "id": 4,
                },
            )
    call_args = mock_router.route.call_args[0][0]
    assert call_args.model == "groq"


# ---------------------------------------------------------------------------
# POST /mcp — JSON-RPC 2.0 tools/call providers_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jsonrpc_tools_call_providers_status():
    with patch("routes.mcp.get_router") as mock_get:
        mock_router = MagicMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=mock_statuses())
        mock_get.return_value = mock_router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "providers_status", "arguments": {}},
                    "id": 5,
                },
            )
    data = r.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 5
    text = data["result"]["content"][0]["text"]
    parsed = json.loads(text)
    assert isinstance(parsed, list)
    assert parsed[0]["name"] == "groq"


# ---------------------------------------------------------------------------
# POST /mcp — erreurs JSON-RPC 2.0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jsonrpc_method_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "nonexistent", "params": {}, "id": 9},
        )
    data = r.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 9
    assert data["error"]["code"] == -32601
    assert "not found" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_jsonrpc_unknown_tool():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "does_not_exist", "arguments": {}},
                "id": 10,
            },
        )
    data = r.json()
    assert data["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_jsonrpc_id_echo():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 42},
        )
    assert r.json()["id"] == 42


@pytest.mark.asyncio
async def test_jsonrpc_invalid_version():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp",
            json={"jsonrpc": "1.0", "method": "initialize", "params": {}, "id": 1},
        )
    data = r.json()
    assert data["error"]["code"] == -32600
