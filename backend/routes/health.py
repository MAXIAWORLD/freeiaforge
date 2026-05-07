from __future__ import annotations

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
