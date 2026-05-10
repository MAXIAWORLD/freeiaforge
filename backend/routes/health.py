from __future__ import annotations

import time

from fastapi import APIRouter
from core.models import ProviderStatus
from routes.chat import get_router

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "freeai-gateway"}


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
            "id": "freeaigate",
            "object": "model",
            "created": created,
            "owned_by": "freeai",
        },
        {
            "id": "freeai-gateway",
            "object": "model",
            "created": created,
            "owned_by": "freeai",
        },
    ]

    seen_ids: set[str] = {"freeaigate", "freeai-gateway"}
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
