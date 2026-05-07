import pytest
from unittest.mock import AsyncMock
from fastapi import HTTPException
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


# --- Phase 3 : error state tracking ---


@pytest.mark.asyncio
async def test_router_tracks_consecutive_errors_on_failure():
    """Après une ProviderError, consecutive_errors doit être incrémenté."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()
    quota.get_status = AsyncMock(return_value=None)  # sera mergé

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
    await router.route(make_request())

    state = router._error_state.get("cerebras", {})
    assert state.get("consecutive_errors", 0) == 1
    assert state.get("last_error") is not None


@pytest.mark.asyncio
async def test_router_resets_consecutive_errors_on_success():
    """Après un succès, consecutive_errors doit repasser à 0."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    provider = AsyncMock()
    provider.name = "groq"
    provider.priority = 1
    provider.complete = AsyncMock(return_value=make_result("groq"))

    router = ProviderRouter(providers=[provider], quota=quota, api_keys={"groq": "key"})
    # Simuler un état d'erreur préalable
    router._error_state["groq"] = {
        "consecutive_errors": 5,
        "last_error": "old",
        "last_used_at": None,
    }

    await router.route(make_request())

    state = router._error_state.get("groq", {})
    assert state.get("consecutive_errors") == 0


@pytest.mark.asyncio
async def test_router_sets_last_used_at_on_success():
    """Après un succès, last_used_at doit être une string ISO datetime."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    provider = AsyncMock()
    provider.name = "groq"
    provider.priority = 1
    provider.complete = AsyncMock(return_value=make_result("groq"))

    router = ProviderRouter(providers=[provider], quota=quota, api_keys={"groq": "key"})
    await router.route(make_request())

    state = router._error_state.get("groq", {})
    assert state.get("last_used_at") is not None
    # Doit être parseable comme ISO datetime
    from datetime import datetime

    datetime.fromisoformat(state["last_used_at"])


# --- Phase 3.5 : signal-based routing ---


def make_long_request(char_count: int) -> ChatRequest:
    """Crée une requête avec un message de char_count caractères."""
    return ChatRequest(messages=[Message(role="user", content="x" * char_count)])


@pytest.mark.asyncio
async def test_router_skips_cerebras_on_long_context():
    """Un message > 24000 chars doit skipper CerebrasProvider silencieusement."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    cerebras = AsyncMock()
    cerebras.name = "cerebras"
    cerebras.priority = 1
    cerebras.complete = AsyncMock(return_value=make_result("cerebras"))

    groq = AsyncMock()
    groq.name = "groq"
    groq.priority = 2
    groq.complete = AsyncMock(return_value=make_result("groq"))

    router = ProviderRouter(
        providers=[cerebras, groq],
        quota=quota,
        api_keys={"cerebras": "k1", "groq": "k2"},
    )
    result = await router.route(make_long_request(25000))

    assert result.provider_name == "groq"
    cerebras.complete.assert_not_called()


@pytest.mark.asyncio
async def test_router_uses_cerebras_on_short_context():
    """Un message <= 24000 chars doit tenter Cerebras en premier."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    cerebras = AsyncMock()
    cerebras.name = "cerebras"
    cerebras.priority = 1
    cerebras.complete = AsyncMock(return_value=make_result("cerebras"))

    router = ProviderRouter(
        providers=[cerebras],
        quota=quota,
        api_keys={"cerebras": "k1"},
    )
    result = await router.route(make_long_request(100))

    assert result.provider_name == "cerebras"
    cerebras.complete.assert_called_once()


@pytest.mark.asyncio
async def test_router_model_hint_groq_uses_only_groq():
    """model='groq' → seul GroqProvider doit être tenté."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    cerebras = AsyncMock()
    cerebras.name = "cerebras"
    cerebras.priority = 1
    cerebras.complete = AsyncMock(return_value=make_result("cerebras"))

    groq = AsyncMock()
    groq.name = "groq"
    groq.priority = 2
    groq.complete = AsyncMock(return_value=make_result("groq"))

    router = ProviderRouter(
        providers=[cerebras, groq],
        quota=quota,
        api_keys={"cerebras": "k1", "groq": "k2"},
    )
    request = ChatRequest(
        model="groq", messages=[Message(role="user", content="hello")]
    )
    result = await router.route(request)

    assert result.provider_name == "groq"
    cerebras.complete.assert_not_called()
    groq.complete.assert_called_once()


@pytest.mark.asyncio
async def test_router_model_hint_unknown_provider_raises_503():
    """model='unknownprovider' avec quota épuisé → HTTPException 503."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=False)

    router = ProviderRouter(
        providers=[],
        quota=quota,
        api_keys={},
    )
    request = ChatRequest(
        model="groq", messages=[Message(role="user", content="hello")]
    )
    with pytest.raises(HTTPException) as exc_info:
        await router.route(request)

    assert exc_info.value.status_code == 503
    assert "groq" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_router_model_hint_no_key_raises_503():
    """model='cerebras' mais pas de clé → HTTPException 503."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)

    cerebras = AsyncMock()
    cerebras.name = "cerebras"
    cerebras.priority = 1

    router = ProviderRouter(
        providers=[cerebras],
        quota=quota,
        api_keys={},  # pas de clé
    )
    request = ChatRequest(
        model="cerebras", messages=[Message(role="user", content="hello")]
    )
    with pytest.raises(HTTPException) as exc_info:
        await router.route(request)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_router_vision_request_skips_non_gemini():
    """Message avec image → seul Gemini doit être tenté."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    cerebras = AsyncMock()
    cerebras.name = "cerebras"
    cerebras.priority = 1
    cerebras.complete = AsyncMock(return_value=make_result("cerebras"))

    groq = AsyncMock()
    groq.name = "groq"
    groq.priority = 2
    groq.complete = AsyncMock(return_value=make_result("groq"))

    gemini = AsyncMock()
    gemini.name = "gemini"
    gemini.priority = 3
    gemini.complete = AsyncMock(return_value=make_result("gemini"))

    router = ProviderRouter(
        providers=[cerebras, groq, gemini],
        quota=quota,
        api_keys={"cerebras": "k1", "groq": "k2", "gemini": "k3"},
    )

    # Message multimodal : content est une list[dict] avec une image
    vision_message = Message(
        role="user",
        content=[  # type: ignore[arg-type]
            {"type": "text", "text": "What's in this image?"},
            {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
        ],
    )
    request = ChatRequest(messages=[vision_message])
    result = await router.route(request)

    assert result.provider_name == "gemini"
    cerebras.complete.assert_not_called()
    groq.complete.assert_not_called()
    gemini.complete.assert_called_once()
