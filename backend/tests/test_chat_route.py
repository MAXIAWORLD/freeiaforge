import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
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


@pytest.mark.asyncio
async def test_chat_completions_returns_200():
    with patch("routes.chat.get_router") as mock_get:
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
    with patch("routes.chat.get_router") as mock_get:
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
