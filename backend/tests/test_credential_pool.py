"""TDD — CredentialPool (Phase A jour 2 freeaigate v0.6.0)

Multi-key pool per provider with rotation + 24h cooldown on key-level errors.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# Construction & key registration
# ---------------------------------------------------------------------------


def test_pool_starts_empty():
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    assert pool.has_keys("groq") is False


def test_pool_add_keys_registers_keys():
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2", "k3"])
    assert pool.has_keys("groq") is True


def test_pool_add_keys_filters_empty_strings():
    """Empty strings (from `,,key1,,key2` typos) must be skipped."""
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["", "k1", "", "k2", ""])
    assert pool.has_keys("groq") is True


def test_pool_add_keys_with_only_empty_strings_keeps_provider_unregistered():
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["", ""])
    assert pool.has_keys("groq") is False


# ---------------------------------------------------------------------------
# Rotation: fill_first
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_returns_first_key_when_all_healthy():
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2", "k3"])
    assert await pool.next_key("groq") == "k1"


@pytest.mark.asyncio
async def test_pool_returns_none_when_provider_not_registered():
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    assert await pool.next_key("groq") is None


@pytest.mark.asyncio
async def test_pool_skips_keys_in_cooldown():
    """First key on cooldown → next_key returns the second."""
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2", "k3"])
    await pool.mark_failure("groq", "k1", 402)
    assert await pool.next_key("groq") == "k2"


@pytest.mark.asyncio
async def test_pool_returns_none_when_all_keys_in_cooldown():
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2"])
    await pool.mark_failure("groq", "k1", 402)
    await pool.mark_failure("groq", "k2", 401)
    assert await pool.next_key("groq") is None


# ---------------------------------------------------------------------------
# mark_failure: cooldown triggers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_marks_failure_402_triggers_cooldown():
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2"])
    await pool.mark_failure("groq", "k1", 402)
    assert await pool.next_key("groq") == "k2"


@pytest.mark.asyncio
async def test_pool_marks_failure_401_triggers_cooldown():
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2"])
    await pool.mark_failure("groq", "k1", 401)
    assert await pool.next_key("groq") == "k2"


@pytest.mark.asyncio
async def test_pool_marks_failure_429_triggers_cooldown():
    """429 Too Many Requests → key-level rate limit, cool it down."""
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2"])
    await pool.mark_failure("groq", "k1", 429)
    assert await pool.next_key("groq") == "k2"


@pytest.mark.asyncio
async def test_pool_marks_failure_503_does_not_trigger_cooldown():
    """503 = provider-side outage, NOT a key issue. Don't waste the key's cooldown."""
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2"])
    await pool.mark_failure("groq", "k1", 503)
    assert await pool.next_key("groq") == "k1"  # k1 stays primary


@pytest.mark.asyncio
async def test_pool_marks_failure_500_does_not_trigger_cooldown():
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2"])
    await pool.mark_failure("groq", "k1", 500)
    assert await pool.next_key("groq") == "k1"


@pytest.mark.asyncio
async def test_pool_marks_failure_none_status_does_not_trigger_cooldown():
    """Network error with no status code → not a key issue."""
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2"])
    await pool.mark_failure("groq", "k1", None)
    assert await pool.next_key("groq") == "k1"


# ---------------------------------------------------------------------------
# mark_success: clears cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_mark_success_clears_cooldown():
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1"])
    await pool.mark_failure("groq", "k1", 402)
    assert await pool.next_key("groq") is None
    await pool.mark_success("groq", "k1")
    assert await pool.next_key("groq") == "k1"


# ---------------------------------------------------------------------------
# Cooldown expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_cooldown_expires_after_24h(monkeypatch):
    """A key on cooldown becomes available again after 24h."""
    from services import credential_pool as cp_module

    pool = cp_module.CredentialPool()
    pool.add_keys("groq", ["k1"])

    real_now = datetime.now(tz=timezone.utc)
    await pool.mark_failure("groq", "k1", 402)
    assert await pool.next_key("groq") is None

    # Simulate 25 hours later
    future = real_now + timedelta(hours=25)
    monkeypatch.setattr(
        cp_module, "_utcnow", lambda: future
    )
    assert await pool.next_key("groq") == "k1"


# ---------------------------------------------------------------------------
# Isolation between providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_isolates_providers():
    """Cooldown on one provider doesn't affect another provider's keys."""
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1"])
    pool.add_keys("cerebras", ["c1"])
    await pool.mark_failure("groq", "k1", 402)
    assert await pool.next_key("groq") is None
    assert await pool.next_key("cerebras") == "c1"


@pytest.mark.asyncio
async def test_pool_mark_failure_on_unknown_key_is_noop():
    """Marking a key that doesn't exist must not crash or affect other keys."""
    from services.credential_pool import CredentialPool

    pool = CredentialPool()
    pool.add_keys("groq", ["k1"])
    await pool.mark_failure("groq", "nonexistent", 402)
    assert await pool.next_key("groq") == "k1"


# ---------------------------------------------------------------------------
# Integration with ProviderRouter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_dispatches_with_pool_supplied_key():
    """When credential_pool is passed, router must call provider.complete with pool.next_key()."""
    from unittest.mock import AsyncMock
    from services.router import ProviderRouter
    from services.credential_pool import CredentialPool
    from core.models import ChatRequest, ChatResponse, ChatChoice, ChatUsage, Message
    from providers.base import ProviderResult

    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    captured: dict[str, str] = {}

    async def _complete(req, key):
        captured["key"] = key
        return ProviderResult(
            response=ChatResponse(
                id="x",
                model="m",
                choices=[
                    ChatChoice(
                        index=0,
                        message=Message(role="assistant", content="ok"),
                        finish_reason="stop",
                    )
                ],
                usage=ChatUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            ),
            provider_name="groq",
            tokens_used=2,
        )

    provider = AsyncMock()
    provider.name = "groq"
    provider.priority = 2
    provider.complete = AsyncMock(side_effect=_complete)

    pool = CredentialPool()
    pool.add_keys("groq", ["pool-k1", "pool-k2"])

    router = ProviderRouter(
        providers=[provider], quota=quota, credential_pool=pool
    )
    request = ChatRequest(messages=[Message(role="user", content="hi")])
    await router.route(request)
    assert captured["key"] == "pool-k1"


@pytest.mark.asyncio
async def test_router_marks_pool_cooldown_on_provider_error_402():
    """On ProviderError(402), the failing key must be put on cooldown so the
    next dispatch picks the next key in the pool."""
    from unittest.mock import AsyncMock
    from services.router import ProviderRouter
    from services.credential_pool import CredentialPool
    from core.models import ChatRequest, Message
    from providers.base import ProviderError

    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    provider = AsyncMock()
    provider.name = "groq"
    provider.priority = 2
    provider.complete = AsyncMock(
        side_effect=ProviderError("groq", status_code=402, reason="quota")
    )

    pool = CredentialPool()
    pool.add_keys("groq", ["bad-k", "good-k"])

    router = ProviderRouter(
        providers=[provider], quota=quota, credential_pool=pool
    )
    request = ChatRequest(messages=[Message(role="user", content="hi")])

    # All providers exhausted because the only one (groq) keeps raising.
    with pytest.raises(RuntimeError):
        await router.route(request)

    # bad-k should now be on cooldown → pool serves good-k
    assert await pool.next_key("groq") == "good-k"
