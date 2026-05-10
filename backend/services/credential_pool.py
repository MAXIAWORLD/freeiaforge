"""CredentialPool — multi-key rotation with 24h cooldown on key-level errors.

Phase A jour 2 (freeaigate v0.6.0). State can either live purely in memory
(unit-test friendly) or be persisted in SQLite via the optional ``db`` arg
so cooldowns survive restarts.

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

Persistence safety: the api_key itself is NEVER stored — only its SHA-256
hash, which the pool uses to match restored rows back to live keys at boot.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite


_COOLDOWN_DURATION = timedelta(hours=24)
_COOLDOWN_TRIGGERS: frozenset[int] = frozenset({401, 402, 429})


def _utcnow() -> datetime:
    """Indirection so tests can monkeypatch the clock."""
    return datetime.now(tz=timezone.utc)


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


@dataclass
class _KeyState:
    api_key: str
    api_key_hash: str = field(default="")
    cooldown_until: datetime | None = None
    fail_count: int = 0


class CredentialPool:
    def __init__(self, db: "aiosqlite.Connection | None" = None) -> None:
        self._keys: dict[str, list[_KeyState]] = {}
        self._lock = asyncio.Lock()
        self._db = db

    def add_keys(self, provider: str, keys: list[str]) -> None:
        clean = [k for k in keys if k]
        if not clean:
            return
        self._keys[provider] = [
            _KeyState(api_key=k, api_key_hash=_hash_key(k)) for k in clean
        ]

    def has_keys(self, provider: str) -> bool:
        return bool(self._keys.get(provider))

    def list_keys(self, provider: str) -> list[str]:
        """Return the api_keys registered for ``provider`` in fill_first order.

        Useful for boot-time validation: callers iterate the keys, probe each
        one, and call ``mark_failure`` on the rejected ones so the next
        ``next_key`` skips straight to a healthy key.
        """
        return [state.api_key for state in self._keys.get(provider, [])]

    async def restore(self) -> None:
        """Load persisted cooldowns from SQLite into in-memory state.

        Safe to call without a db (no-op). Should be invoked AFTER add_keys
        so the pool can match persisted rows back to live keys via the hash.
        """
        if self._db is None:
            return
        async with self._db.execute(
            "SELECT provider, key_hash, cooldown_until, fail_count "
            "FROM credential_pool_state"
        ) as cursor:
            rows = await cursor.fetchall()
        for provider, key_hash, cooldown_iso, fail_count in rows:
            for state in self._keys.get(provider, []):
                if state.api_key_hash == key_hash:
                    state.cooldown_until = (
                        datetime.fromisoformat(cooldown_iso) if cooldown_iso else None
                    )
                    state.fail_count = fail_count
                    break

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
                    if self._db is not None:
                        await self._persist_state(provider, state)
                    return

    async def mark_success(self, provider: str, api_key: str) -> None:
        async with self._lock:
            for state in self._keys.get(provider, []):
                if state.api_key == api_key:
                    had_state = (
                        state.cooldown_until is not None or state.fail_count > 0
                    )
                    state.cooldown_until = None
                    state.fail_count = 0
                    if self._db is not None and had_state:
                        await self._clear_state(provider, state.api_key_hash)
                    return

    async def _persist_state(self, provider: str, state: _KeyState) -> None:
        cooldown_iso = (
            state.cooldown_until.isoformat() if state.cooldown_until else None
        )
        await self._db.execute(
            """
            INSERT INTO credential_pool_state
                (provider, key_hash, cooldown_until, fail_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(provider, key_hash) DO UPDATE SET
                cooldown_until = excluded.cooldown_until,
                fail_count = excluded.fail_count
            """,
            (provider, state.api_key_hash, cooldown_iso, state.fail_count),
        )
        await self._db.commit()

    async def _clear_state(self, provider: str, key_hash: str) -> None:
        await self._db.execute(
            "DELETE FROM credential_pool_state WHERE provider=? AND key_hash=?",
            (provider, key_hash),
        )
        await self._db.commit()
