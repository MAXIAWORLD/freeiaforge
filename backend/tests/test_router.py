import pytest
from unittest.mock import AsyncMock
from services.router import ProviderRouter
from core.models import ChatRequest, ChatResponse, ChatChoice, ChatUsage, Message
from providers.base import ProviderError, ProviderResult


def make_result(provider_name: str) -> ProviderResult:
    return ProviderResult(
        response=ChatResponse(
            id="test-id",
            model="llama",
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role="assistant", content="hello"),
                    finish_reason="stop",
                )
            ],
            usage=ChatUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        ),
        provider_name=provider_name,
        tokens_used=15,
    )


def make_request() -> ChatRequest:
    return ChatRequest(messages=[Message(role="user", content="hi")])


@pytest.mark.asyncio
async def test_router_uses_first_available_provider():
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    provider = AsyncMock()
    provider.name = "cerebras"
    provider.priority = 1
    provider.complete = AsyncMock(return_value=make_result("cerebras"))

    router = ProviderRouter(
        providers=[provider], quota=quota, api_keys={"cerebras": "key"}
    )
    result = await router.route(make_request())

    assert result.provider_name == "cerebras"
    provider.complete.assert_called_once()


@pytest.mark.asyncio
async def test_router_skips_quota_exhausted_provider():
    quota = AsyncMock()
    quota.is_available = AsyncMock(side_effect=[False, True])
    quota.record_usage = AsyncMock()

    p1 = AsyncMock()
    p1.name = "cerebras"
    p1.priority = 1
    p1.complete = AsyncMock(return_value=make_result("cerebras"))

    p2 = AsyncMock()
    p2.name = "groq"
    p2.priority = 2
    p2.complete = AsyncMock(return_value=make_result("groq"))

    router = ProviderRouter(
        providers=[p1, p2], quota=quota, api_keys={"cerebras": "k1", "groq": "k2"}
    )
    result = await router.route(make_request())

    assert result.provider_name == "groq"
    p1.complete.assert_not_called()
    p2.complete.assert_called_once()


@pytest.mark.asyncio
async def test_router_falls_back_on_provider_error():
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    p1 = AsyncMock()
    p1.name = "cerebras"
    p1.priority = 1
    p1.complete = AsyncMock(side_effect=ProviderError("cerebras", status_code=429))

    p2 = AsyncMock()
    p2.name = "groq"
    p2.priority = 2
    p2.complete = AsyncMock(return_value=make_result("groq"))

    router = ProviderRouter(
        providers=[p1, p2], quota=quota, api_keys={"cerebras": "k1", "groq": "k2"}
    )
    result = await router.route(make_request())

    assert result.provider_name == "groq"


@pytest.mark.asyncio
async def test_router_raises_when_all_providers_exhausted():
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=False)

    p1 = AsyncMock()
    p1.name = "cerebras"
    p1.priority = 1

    router = ProviderRouter(providers=[p1], quota=quota, api_keys={"cerebras": "k"})

    with pytest.raises(RuntimeError, match="All providers exhausted"):
        await router.route(make_request())


@pytest.mark.asyncio
async def test_router_skips_provider_with_no_api_key():
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    p1 = AsyncMock()
    p1.name = "cerebras"
    p1.priority = 1
    p1.complete = AsyncMock()

    p2 = AsyncMock()
    p2.name = "groq"
    p2.priority = 2
    p2.complete = AsyncMock(return_value=make_result("groq"))

    # cerebras has no key
    router = ProviderRouter(providers=[p1, p2], quota=quota, api_keys={"groq": "k2"})
    result = await router.route(make_request())

    assert result.provider_name == "groq"
    p1.complete.assert_not_called()


@pytest.mark.asyncio
async def test_router_records_usage_on_success():
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    provider = AsyncMock()
    provider.name = "groq"
    provider.priority = 2
    provider.complete = AsyncMock(return_value=make_result("groq"))

    router = ProviderRouter(providers=[provider], quota=quota, api_keys={"groq": "key"})
    await router.route(make_request())

    quota.record_usage.assert_called_once_with("groq", requests=1, tokens=15)
