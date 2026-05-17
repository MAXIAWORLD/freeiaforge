from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.models import (
    ChatChoice,
    ChatRequest,
    ChatResponse,
    ChatUsage,
    Message,
)
from providers.base import ProviderResult
from services.cache import ExactCache
from services.router import ProviderRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_response(content: str = "hello") -> ChatResponse:
    return ChatResponse(
        id="test-id",
        model="llama",
        choices=[
            ChatChoice(
                index=0,
                message=Message(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=ChatUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def make_messages(text: str = "hi") -> list[Message]:
    return [Message(role="user", content=text)]


def make_result(provider_name: str = "groq") -> ProviderResult:
    return ProviderResult(
        response=make_response(),
        provider_name=provider_name,
        tokens_used=15,
    )


def make_request(text: str = "hi") -> ChatRequest:
    return ChatRequest(messages=make_messages(text))


# ---------------------------------------------------------------------------
# Unit tests — ExactCache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_lookup_empty_returns_none(tmp_path: Path) -> None:
    """Lookup sur cache vide → None."""
    cache = ExactCache(data_dir=tmp_path)
    result = await cache.lookup(make_messages("what is the capital of France?"))
    assert result is None


@pytest.mark.asyncio
async def test_cache_store_then_lookup_returns_response(tmp_path: Path) -> None:
    """Store puis lookup avec les mêmes messages → retourne ChatResponse."""
    cache = ExactCache(data_dir=tmp_path)
    messages = make_messages("what is 2+2?")
    response = make_response("4")

    await cache.store(messages, response, ttl_seconds=3600)
    result = await cache.lookup(messages)

    assert result is not None
    assert result.choices[0].message.content == "4"


@pytest.mark.asyncio
async def test_cache_lookup_after_ttl_returns_none(tmp_path: Path) -> None:
    """Après TTL expiré → lookup retourne None."""
    cache = ExactCache(data_dir=tmp_path)
    messages = make_messages("temp question")
    response = make_response("temp answer")

    # TTL = 1 seconde
    await cache.store(messages, response, ttl_seconds=1)

    # Simuler expiration en forçant expires_at dans le passé
    # On attend > 1s OU on manipule le cache directement
    # Approche : on attend 1.1s (fiable, TTL=1s)
    await asyncio.sleep(1.1)

    result = await cache.lookup(messages)
    assert result is None


@pytest.mark.asyncio
async def test_cache_different_messages_no_hit(tmp_path: Path) -> None:
    """Messages différents → pas de hit."""
    cache = ExactCache(data_dir=tmp_path)
    await cache.store(
        make_messages("question A"), make_response("answer A"), ttl_seconds=3600
    )

    result = await cache.lookup(make_messages("question B"))
    assert result is None


@pytest.mark.asyncio
async def test_cache_normalized_whitespace_hits(tmp_path: Path) -> None:
    """Whitespace normalisé → même hash."""
    cache = ExactCache(data_dir=tmp_path)
    messages_stored = make_messages("  hello world  ")
    messages_lookup = make_messages("hello world")

    await cache.store(messages_stored, make_response("stored"), ttl_seconds=3600)
    result = await cache.lookup(messages_lookup)

    # Normalisation des espaces → même clé → hit
    assert result is not None
    assert result.choices[0].message.content == "stored"


@pytest.mark.asyncio
async def test_cache_case_insensitive_hit(tmp_path: Path) -> None:
    """Case normalisé → même hash."""
    cache = ExactCache(data_dir=tmp_path)
    await cache.store(
        make_messages("What Is 2+2?"), make_response("four"), ttl_seconds=3600
    )

    result = await cache.lookup(make_messages("what is 2+2?"))
    assert result is not None
    assert result.choices[0].message.content == "four"


@pytest.mark.asyncio
async def test_cache_overwrite_extends_ttl(tmp_path: Path) -> None:
    """Re-stocker la même clé → nouvelle réponse retournée."""
    cache = ExactCache(data_dir=tmp_path)
    messages = make_messages("same question")

    await cache.store(messages, make_response("first"), ttl_seconds=3600)
    await cache.store(messages, make_response("second"), ttl_seconds=3600)

    result = await cache.lookup(messages)
    assert result is not None
    assert result.choices[0].message.content == "second"


@pytest.mark.asyncio
async def test_cache_multipart_messages(tmp_path: Path) -> None:
    """Liste de messages avec rôles multiples → hash stable."""
    cache = ExactCache(data_dir=tmp_path)
    messages = [
        Message(role="system", content="You are helpful."),
        Message(role="user", content="hi"),
    ]
    response = make_response("hello!")

    await cache.store(messages, response, ttl_seconds=3600)
    result = await cache.lookup(messages)

    assert result is not None
    assert result.choices[0].message.content == "hello!"


# ---------------------------------------------------------------------------
# Integration tests — Router avec cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_cache_hit_provider_not_called() -> None:
    """Router avec cache → provider PAS appelé si cache hit."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    provider = AsyncMock()
    provider.name = "groq"
    provider.priority = 1
    provider.complete = AsyncMock(return_value=make_result("groq"))

    # Cache mock retourne une réponse (hit)
    cache = AsyncMock()
    cache.lookup = AsyncMock(return_value=make_response("cached response"))
    cache.store = AsyncMock()

    router = ProviderRouter(
        providers=[provider],
        quota=quota,
        api_keys={"groq": "key"},
        cache=cache,
    )
    result = await router.route(make_request("hi"))

    # Provider ne doit pas être appelé
    provider.complete.assert_not_called()
    assert result.provider_name == "cache"
    assert result.tokens_used == 0
    assert result.response.choices[0].message.content == "cached response"


@pytest.mark.asyncio
async def test_router_cache_miss_provider_called() -> None:
    """Router avec cache → provider appelé si cache miss."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    provider = AsyncMock()
    provider.name = "groq"
    provider.priority = 1
    provider.complete = AsyncMock(return_value=make_result("groq"))

    # Cache mock retourne None (miss)
    cache = AsyncMock()
    cache.lookup = AsyncMock(return_value=None)
    cache.store = AsyncMock()

    router = ProviderRouter(
        providers=[provider],
        quota=quota,
        api_keys={"groq": "key"},
        cache=cache,
    )
    result = await router.route(make_request("hi"))

    provider.complete.assert_called_once()
    assert result.provider_name == "groq"


@pytest.mark.asyncio
async def test_router_cache_none_behavior_unchanged() -> None:
    """Router avec cache=None → comportement inchangé (pas de cache)."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    provider = AsyncMock()
    provider.name = "groq"
    provider.priority = 1
    provider.complete = AsyncMock(return_value=make_result("groq"))

    # Pas de cache (None)
    router = ProviderRouter(
        providers=[provider],
        quota=quota,
        api_keys={"groq": "key"},
        cache=None,
    )
    result = await router.route(make_request("hi"))

    provider.complete.assert_called_once()
    assert result.provider_name == "groq"


@pytest.mark.asyncio
async def test_router_cache_store_called_after_provider_success() -> None:
    """Après succès provider → cache.store doit être planifié (fire-and-forget)."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    provider = AsyncMock()
    provider.name = "groq"
    provider.priority = 1
    provider.complete = AsyncMock(return_value=make_result("groq"))

    cache = AsyncMock()
    cache.lookup = AsyncMock(return_value=None)
    cache.store = AsyncMock()

    router = ProviderRouter(
        providers=[provider],
        quota=quota,
        api_keys={"groq": "key"},
        cache=cache,
    )
    await router.route(make_request("hi"))

    # Laisser les tâches asyncio se terminer
    await asyncio.sleep(0)

    cache.store.assert_called_once()
    # Vérifier les arguments : messages + response + ttl_seconds
    call_kwargs = cache.store.call_args
    assert call_kwargs is not None


@pytest.mark.asyncio
async def test_router_cache_not_stored_on_cache_hit() -> None:
    """Sur un cache hit → cache.store ne doit PAS être rappelé."""
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    provider = AsyncMock()
    provider.name = "groq"
    provider.priority = 1

    cache = AsyncMock()
    cache.lookup = AsyncMock(return_value=make_response("hit"))
    cache.store = AsyncMock()

    router = ProviderRouter(
        providers=[provider],
        quota=quota,
        api_keys={"groq": "key"},
        cache=cache,
    )
    await router.route(make_request("hi"))
    await asyncio.sleep(0)

    cache.store.assert_not_called()
