from __future__ import annotations

import time

from fastapi import APIRouter, Request
from core.models import ProviderStatus
from routes.chat import get_router
from services.stats_history import get_last_7_days

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    try:
        r = get_router()
        providers_count = len(getattr(r, "_providers", []))
    except RuntimeError:
        providers_count = 0
    return {
        "status": "ok",
        "service": "freeai-gateway",
        "version": request.app.version,
        "providers": providers_count,
    }


@router.get("/v1/quota")
async def quota() -> dict:
    r = get_router()
    statuses = await r.get_provider_statuses()
    daily_stats = r.get_daily_stats()
    stats_db = getattr(r, "_stats_db", None)
    history = await get_last_7_days(stats_db) if stats_db is not None else []
    return {
        "providers": [s.model_dump() for s in statuses],
        "daily_stats": daily_stats,
        "history": history,
    }


async def _providers_handler() -> list[ProviderStatus]:
    return await get_router().get_provider_statuses()


@router.get("/v1/providers", response_model=list[ProviderStatus])
async def providers() -> list[ProviderStatus]:
    return await _providers_handler()


@router.get("/v1/providers/status", response_model=list[ProviderStatus])
async def providers_status() -> list[ProviderStatus]:
    return await _providers_handler()


@router.get("/v1/models")
async def models() -> dict:
    created = int(time.time())
    router_instance = get_router()
    api_keys = getattr(router_instance, "_api_keys", {})
    providers = getattr(router_instance, "_providers", [])

    data: list[dict] = [
        {
            "id": "freeai-gateway",
            "object": "model",
            "created": created,
            "owned_by": "freeai",
        }
    ]

    seen_ids: set[str] = {"freeai-gateway"}
    for provider in providers:
        if provider.name == "ollama" or api_keys.get(provider.name):
            model_id = getattr(provider, "default_model", None)
            if model_id and model_id not in seen_ids:
                data.append(
                    {
                        "id": model_id,
                        "object": "model",
                        "created": created,
                        "owned_by": provider.name,
                    }
                )
                seen_ids.add(model_id)

    return {"object": "list", "data": data}
