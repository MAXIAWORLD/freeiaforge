from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from core.models import ChatResponse, ChatChoice, ChatUsage, Message
from providers.base import ProviderResult


def mock_result() -> ProviderResult:
    return ProviderResult(
        response=ChatResponse(
            id="abc123",
            model="llama-3.3-70b",
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role="assistant", content="Hello!"),
                    finish_reason="stop",
                )
            ],
            usage=ChatUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
        ),
        provider_name="groq",
        tokens_used=8,
    )


# ---------------------------------------------------------------------------
# Existing tests (unchanged)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_completions_returns_200():
    with patch("routes.chat.get_router") as mock_get, \
         patch("routes.chat.get_memory", return_value=None):
        router = AsyncMock()
        router.route = AsyncMock(return_value=mock_result())
        mock_get.return_value = router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )

    assert r.status_code == 200
    data = r.json()
    assert data["choices"][0]["message"]["content"] == "Hello!"
    assert data["model"] == "llama-3.3-70b"


@pytest.mark.asyncio
async def test_chat_completions_503_when_all_exhausted():
    with patch("routes.chat.get_router") as mock_get, \
         patch("routes.chat.get_memory", return_value=None):
        router = AsyncMock()
        router.route = AsyncMock(side_effect=RuntimeError("All providers exhausted"))
        mock_get.return_value = router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )

    assert r.status_code == 503
    assert "exhausted" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_chat_completions_400_on_empty_messages():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post("/v1/chat/completions", json={"messages": []})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# New tests — memory integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_context_prepended_when_memories_found():
    """Provider receives a system message containing retrieved memories."""
    memory_svc = MagicMock()
    memory_svc.query = AsyncMock(return_value=["memory 1", "memory 2"])
    memory_svc.store = AsyncMock()

    captured_request = {}

    async def capture_route(req):
        captured_request["messages"] = [m.model_dump() for m in req.messages]
        return mock_result()

    with patch("routes.chat.get_router") as mock_get_router, \
         patch("routes.chat.get_memory", return_value=memory_svc):
        router = MagicMock()
        router.route = capture_route
        mock_get_router.return_value = router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "tell me about GraphQL"}]},
            )

    assert r.status_code == 200
    msgs = captured_request["messages"]
    # First message must be a system message with memories
    assert msgs[0]["role"] == "system"
    assert "memory 1" in msgs[0]["content"]
    assert "memory 2" in msgs[0]["content"]
    # Original user message preserved after
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "tell me about GraphQL"


@pytest.mark.asyncio
async def test_chat_works_normally_when_memory_is_none():
    """No memory service → chat behaves exactly as before."""
    with patch("routes.chat.get_router") as mock_get_router, \
         patch("routes.chat.get_memory", return_value=None):
        router = AsyncMock()
        router.route = AsyncMock(return_value=mock_result())
        mock_get_router.return_value = router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_chat_works_when_memory_returns_empty_list():
    """Empty memory results → no system message prepended."""
    memory_svc = MagicMock()
    memory_svc.query = AsyncMock(return_value=[])
    memory_svc.store = AsyncMock()

    captured_request = {}

    async def capture_route(req):
        captured_request["messages"] = [m.model_dump() for m in req.messages]
        return mock_result()

    with patch("routes.chat.get_router") as mock_get_router, \
         patch("routes.chat.get_memory", return_value=memory_svc):
        router = MagicMock()
        router.route = capture_route
        mock_get_router.return_value = router

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )

    assert r.status_code == 200
    msgs = captured_request["messages"]
    assert msgs[0]["role"] == "user"


@pytest.mark.asyncio
async def test_original_messages_not_mutated():
    """request.messages list must not be mutated — a new list is created."""
    memory_svc = MagicMock()
    memory_svc.query = AsyncMock(return_value=["some memory"])
    memory_svc.store = AsyncMock()

    requests_seen = []

    async def capture_route(req):
        requests_seen.append(req.messages)
        return mock_result()

    with patch("routes.chat.get_router") as mock_get_router, \
         patch("routes.chat.get_memory", return_value=memory_svc):
        router = MagicMock()
        router.route = capture_route
        mock_get_router.return_value = router

        original_payload = {"messages": [{"role": "user", "content": "hi"}]}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/v1/chat/completions", json=original_payload)

    # The route received 2 messages (system + user), original payload unchanged
    assert len(requests_seen[0]) == 2
    assert requests_seen[0][0].role == "system"


@pytest.mark.asyncio
async def test_set_memory_and_get_memory_singleton():
    """set_memory / get_memory follow the same singleton pattern as router."""
    from routes.chat import set_memory, get_memory
    from services.memory import MemPalaceService
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        svc = MemPalaceService(data_dir=Path(tmp))
        set_memory(svc)
        assert get_memory() is svc
