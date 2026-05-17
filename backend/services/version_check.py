from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_VERSION_URL = "https://raw.githubusercontent.com/maxiaworld/freeiaforge/main/VERSION"


async def check_version(current_version: str) -> None:
    """Log a notice if a newer version is available. Fails silently."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(_VERSION_URL)
            r.raise_for_status()
            latest = r.text.strip()
            if latest != current_version:
                logger.info(
                    "⚡ FreeAI v%s available — docker pull maxiaworld/freeiaforge:latest",
                    latest,
                )
    except Exception:
        pass
