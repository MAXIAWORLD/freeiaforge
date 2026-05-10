"""CredentialPool — multi-key rotation with 24h cooldown on key-level errors.

Phase A jour 2 (freeaigate v0.6.0). Keeps state in memory; SQLite persistence
lives in a follow-up commit so this module can be unit-tested in isolation.

Selection strategy: ``fill_first`` — the first key whose cooldown has expired
is returned. Failover to the next key happens transparently when the current
one is marked as failed with a key-level status code.

Cooldown triggers (key-level errors):
    401 Unauthorized       → key is invalid or revoked
    402 Payment Required   → free-tier quota exhausted on that key
    429 Too Many Requests  → key-level rate limit hit

Codes such as 500/503 indicate provider-side trouble and must NOT consume the
key's cooldown — keep the key healthy and fail over to the next provider via
the router's circuit breaker instead.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


_COOLDOWN_DURATION = timedelta(hours=24)
_COOLDOWN_TRIGGERS: frozenset[int] = frozenset({401, 402, 429})


def _utcnow() -> datetime:
    """Indirection so tests can monkeypatch the clock."""
    return datetime.now(tz=timezone.utc)


@dataclass
class _KeyState:
    api_key: str
    cooldown_until: datetime | None = None
    fail_count: int = 0


class CredentialPool:
    def __init__(self) -> None:
        self._keys: dict[str, list[_KeyState]] = {}
        self._lock = asyncio.Lock()

    def add_keys(self, provider: str, keys: list[str]) -> None:
        clean = [k for k in keys if k]
        if not clean:
            return
        self._keys[provider] = [_KeyState(api_key=k) for k in clean]

    def has_keys(self, provider: str) -> bool:
        return bool(self._keys.get(provider))

    async def next_key(self, provider: str) -> str | None:
        async with self._lock:
            now = _utcnow()
            for state in self._keys.get(provider, []):
                if state.cooldown_until is None or state.cooldown_until <= now:
                    return state.api_key
            return None

    async def mark_failure(
        self, provider: str, api_key: str, status_code: int | None
    ) -> None:
        if status_code not in _COOLDOWN_TRIGGERS:
            return
        async with self._lock:
            for state in self._keys.get(provider, []):
                if state.api_key == api_key:
                    state.cooldown_until = _utcnow() + _COOLDOWN_DURATION
                    state.fail_count += 1
                    return

    async def mark_success(self, provider: str, api_key: str) -> None:
        async with self._lock:
            for state in self._keys.get(provider, []):
                if state.api_key == api_key:
                    state.cooldown_until = None
                    state.fail_count = 0
                    return
