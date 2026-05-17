from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from core.models import ChatRequest
from services.router import ProviderRouter
from services.task_inference import infer_task_type

logger = logging.getLogger(__name__)
router = APIRouter()

_router_instance: ProviderRouter | None = None


def set_router(r: ProviderRouter) -> None:
    global _router_instance
    _router_instance = r


def get_router() -> ProviderRouter:
    if _router_instance is None:
        raise RuntimeError("Router not initialized")
    return _router_instance


@router.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest, response: Response):
    if not request.messages:
        raise HTTPException(status_code=400, detail="messages cannot be empty")

    task_type = infer_task_type(request)

    if request.stream:
        try:
            provider_name, gen = await get_router().route_stream(request)
        except RuntimeError as e:
            if "exhausted" in str(e).lower():
                raise HTTPException(status_code=503, detail=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")
        return StreamingResponse(
            gen,
            media_type="text/event-stream",
            headers={
                "X-FreeAI-Provider": provider_name,
                "X-FreeAI-Task": task_type,
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        result = await get_router().route(request)
    except RuntimeError as e:
        if "exhausted" in str(e).lower():
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

    response.headers["X-FreeAI-Provider"] = result.provider_name
    response.headers["X-FreeAI-Task"] = task_type
    return result.response
