"""Boot-time key validation for the CredentialPool.

After the pool is filled with provider keys (and optional persisted state is
restored), each key is probed once to detect outright rejected credentials —
so the first user request doesn't waste a round-trip on a 401. Keys that
fail the probe are pushed onto the pool's 24h cooldown via the standard
``mark_failure(401)`` path; this also persists to SQLite when the pool is
db-backed, so subsequent restarts skip them too.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from providers.base import Provider
    from services.credential_pool import CredentialPool


logger = logging.getLogger(__name__)


async def _validate_one(
    provider: "Provider", api_key: str
) -> tuple[str, bool]:
    """Probe ``api_key`` against ``provider``. Returns (api_key, is_valid)."""
    try:
        ok = await provider.validate_key(api_key)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "[%s] validate_key raised %s; assuming valid", provider.name, exc
        )
        ok = True
    return api_key, ok


async def validate_keys(
    providers: list["Provider"], pool: "CredentialPool"
) -> dict[str, dict[str, int]]:
    """Validate every key registered in ``pool`` for the given providers.

    Returns a per-provider summary ``{provider_name: {valid, invalid}}`` so
    the caller can surface boot-time stats in logs.

    Invalid keys are immediately put on cooldown via ``pool.mark_failure``.
    """
    stats: dict[str, dict[str, int]] = {}

    async def _validate_provider(provider: "Provider") -> None:
        keys = pool.list_keys(provider.name)
        if not keys:
            return
        results = await asyncio.gather(
            *(_validate_one(provider, k) for k in keys)
        )
        valid = invalid = 0
        for api_key, ok in results:
            if ok:
                valid += 1
            else:
                invalid += 1
                await pool.mark_failure(provider.name, api_key, 401)
                logger.warning(
                    "[%s] api_key rejected (401/403) — placed on cooldown",
                    provider.name,
                )
        stats[provider.name] = {"valid": valid, "invalid": invalid}

    await asyncio.gather(*(_validate_provider(p) for p in providers))
    return stats
