from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


async def fetch_providers_config(url: str, local_path: Path) -> dict[str, dict] | None:
    """Fetch providers.json from URL; fall back to local cache on failure.

    Expected JSON shape:
    {
      "cerebras": {"daily_requests": 5000, "daily_tokens": 1000000},
      "groq": {"daily_requests": 14400, "daily_tokens": 500000},
      ...
    }
    Returns the dict, or None if both remote and local fail.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            data: dict = r.json()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.info("providers.json fetched from %s", url)
        return data
    except Exception as exc:
        logger.warning("Failed to fetch providers.json from %s: %s", url, exc)

    if local_path.exists():
        try:
            data = json.loads(local_path.read_text(encoding="utf-8"))
            logger.info("Using local providers.json cache (%s)", local_path)
            return data
        except Exception as exc:
            logger.warning("Failed to read local providers.json %s: %s", local_path, exc)

    return None


def apply_providers_config(limits: dict[str, dict], providers_data: dict[str, dict]) -> dict[str, dict]:
    """Merge providers.json overrides into the limits dict.

    providers_data entries override the matching provider's requests/tokens.
    Unknown providers in providers_data are ignored.
    Returns a new dict (immutable pattern).
    """
    merged = {name: dict(vals) for name, vals in limits.items()}
    for provider, overrides in providers_data.items():
        if provider not in merged:
            continue
        if "daily_requests" in overrides:
            merged[provider]["requests"] = int(overrides["daily_requests"])
        if "daily_tokens" in overrides:
            merged[provider]["tokens"] = int(overrides["daily_tokens"])
    return merged
