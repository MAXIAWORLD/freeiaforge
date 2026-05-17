from __future__ import annotations

import os
import platform
import logging

import httpx

logger = logging.getLogger(__name__)

_COUNTER_URL = "https://maxiaworld.app/freeai"


async def report_startup(
    version: str,
    providers_count: int,
    has_ollama: bool,
) -> None:
    """Send opt-in startup telemetry. Set FREEAI_TELEMETRY=0 to disable."""
    if os.environ.get("FREEAI_TELEMETRY", "1") == "0":
        return
    payload = {
        "version": version,
        "os": platform.system().lower(),
        "providers_count": providers_count,
        "ollama": has_ollama,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(_COUNTER_URL, json=payload)
    except Exception:
        pass
