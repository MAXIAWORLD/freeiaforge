from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from core.models import ChatRequest, ChatResponse, Message
from services.memory import MemPalaceService
from services.router import ProviderRouter

logger = logging.getLogger(__name__)
router = APIRouter()

_router_instance: ProviderRouter | None = None
_memory_instance: MemPalaceService | None = None


def set_router(r: ProviderRouter) -> None:
    global _router_instance
    _router_instance = r


def get_router() -> ProviderRouter:
    if _router_instance is None:
        raise RuntimeError("Router not initialized")
    return _router_instance


def set_memory(m: MemPalaceService) -> None:
    global _memory_instance
    _memory_instance = m


def get_memory() -> MemPalaceService | None:
    return _memory_instance


@router.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(request: ChatRequest) -> ChatResponse:
    if not request.messages:
        raise HTTPException(status_code=400, detail="messages cannot be empty")

    last_user = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        None,
    )

    memory = get_memory()
    messages = list(request.messages)

    if memory is not None and last_user is not None:
        memories = await memory.query(last_user)
        if memories:
            system_content = "Relevant memories:\n" + "\n".join(
                f"- {m}" for m in memories
            )
            messages = [Message(role="system", content=system_content)] + messages

    augmented = request.model_copy(update={"messages": messages})

    try:
        result = await get_router().route(augmented)
    except RuntimeError as e:
        if "exhausted" in str(e).lower():
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

    if memory is not None and last_user is not None:
        assistant_content = result.response.choices[0].message.content
        asyncio.create_task(memory.store(last_user, assistant_content))

    return result.response
