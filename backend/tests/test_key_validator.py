"""TDD — startup key validation (Phase A jour 4, freeaigate v0.6.0)

After the pool is filled and circuit_state restored, each configured key is
sanity-checked against the provider's /models endpoint. Keys returning
401/403 are placed on cooldown immediately so they don't pollute the first
real user request. Keys reached over a 5xx or transient network error are
left as-is (provider-side issue, not a key issue).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from providers.base import Provider
from services.credential_pool import CredentialPool


class _FakeProvider(Provider):
    name = "fake"
    priority = 1

    def __init__(self, validation_results: dict[str, bool]) -> None:
        self._results = validation_results
        self.calls: list[str] = []

    async def complete(self, request, api_key):  # pragma: no cover
        raise NotImplementedError

    async def validate_key(self, api_key: str) -> bool:
        self.calls.append(api_key)
        return self._results.get(api_key, True)


# ---------------------------------------------------------------------------
# CredentialPool.list_keys helper
# ---------------------------------------------------------------------------


def test_pool_list_keys_returns_registered_keys_in_order():
    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2", "k3"])
    assert pool.list_keys("groq") == ["k1", "k2", "k3"]


def test_pool_list_keys_returns_empty_for_unknown_provider():
    pool = CredentialPool()
    assert pool.list_keys("nonexistent") == []


# ---------------------------------------------------------------------------
# validate_keys orchestrator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_keys_marks_invalid_keys_on_cooldown():
    """A key returning False from validate_key must end up on cooldown."""
    from services.key_validator import validate_keys

    provider = _FakeProvider({"good": True, "bad": False})
    provider.name = "groq"

    pool = CredentialPool()
    pool.add_keys("groq", ["good", "bad"])

    await validate_keys([provider], pool)

    assert await pool.next_key("groq") == "good"


@pytest.mark.asyncio
async def test_validate_keys_leaves_valid_keys_untouched():
    """Valid keys must remain in fill_first order with no cooldown."""
    from services.key_validator import validate_keys

    provider = _FakeProvider({"k1": True, "k2": True, "k3": True})
    provider.name = "groq"

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2", "k3"])

    await validate_keys([provider], pool)
    assert await pool.next_key("groq") == "k1"


@pytest.mark.asyncio
async def test_validate_keys_returns_per_provider_stats():
    """Caller wants a {provider: {valid, invalid}} summary for the boot log."""
    from services.key_validator import validate_keys

    p_groq = _FakeProvider({"a": True, "b": False, "c": True})
    p_groq.name = "groq"
    p_cer = _FakeProvider({"x": True})
    p_cer.name = "cerebras"

    pool = CredentialPool()
    pool.add_keys("groq", ["a", "b", "c"])
    pool.add_keys("cerebras", ["x"])

    stats = await validate_keys([p_groq, p_cer], pool)

    assert stats["groq"]["valid"] == 2
    assert stats["groq"]["invalid"] == 1
    assert stats["cerebras"]["valid"] == 1
    assert stats["cerebras"]["invalid"] == 0


@pytest.mark.asyncio
async def test_validate_keys_handles_provider_with_no_keys():
    """A provider with no keys registered must just be skipped, not crash."""
    from services.key_validator import validate_keys

    provider = _FakeProvider({})
    provider.name = "mistral"

    pool = CredentialPool()  # nothing registered for mistral

    stats = await validate_keys([provider], pool)
    assert "mistral" not in stats or stats["mistral"]["valid"] + stats["mistral"]["invalid"] == 0
    assert provider.calls == []


@pytest.mark.asyncio
async def test_validate_keys_calls_validate_for_every_key():
    from services.key_validator import validate_keys

    provider = _FakeProvider({"k1": True, "k2": True, "k3": True})
    provider.name = "groq"

    pool = CredentialPool()
    pool.add_keys("groq", ["k1", "k2", "k3"])

    await validate_keys([provider], pool)
    assert sorted(provider.calls) == ["k1", "k2", "k3"]


@pytest.mark.asyncio
async def test_validate_keys_default_provider_validate_key_returns_true():
    """The default Provider.validate_key (no override) must return True so
    plain Provider implementations don't accidentally cool down their keys."""
    from providers.base import Provider as BaseProvider

    class _Plain(BaseProvider):
        name = "plain"
        priority = 1

        async def complete(self, request, api_key):  # pragma: no cover
            raise NotImplementedError

    provider = _Plain()
    assert await provider.validate_key("any-key") is True
