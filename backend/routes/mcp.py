from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.models import ChatRequest, Message
from routes.chat import get_router

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# MCP input/output models
# ---------------------------------------------------------------------------


class MCPChatInput(BaseModel):
    messages: list[Message]
    model: str = "auto"


class MCPContent(BaseModel):
    type: str = "text"
    text: str


class MCPToolResponse(BaseModel):
    content: list[MCPContent]


# ---------------------------------------------------------------------------
# MCP manifest (static, no external dependency)
# ---------------------------------------------------------------------------

_MANIFEST: dict = {
    "name": "freeai-gateway",
    "version": "0.2.0",
    "description": "6+ free LLMs behind one OpenAI-compatible API",
    "tools": [
        {
            "name": "chat",
            "description": (
                "Send messages to the best available free LLM. "
                "Auto-fallback across 7 providers."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["role", "content"],
                        },
                        "description": "Conversation messages",
                    },
                    "model": {
                        "type": "string",
                        "default": "auto",
                        "description": (
                            "Provider hint: auto, cerebras, groq, sambanova, "
                            "gemini, huggingface, mistral, openrouter"
                        ),
                    },
                },
                "required": ["messages"],
            },
        },
        {
            "name": "providers_status",
            "description": (
                "Get status of all LLM providers "
                "(quota remaining, errors, availability)."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
    ],
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/mcp")
async def mcp_manifest() -> dict:
    return _MANIFEST


@router.post("/mcp/tools/chat", response_model=MCPToolResponse)
async def mcp_chat(body: MCPChatInput) -> MCPToolResponse:
    request = ChatRequest(model=body.model, messages=body.messages)
    try:
        result = await get_router().route(request)
    except (HTTPException, RuntimeError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return MCPToolResponse(
            content=[MCPContent(type="text", text=f"[error] {detail}")]
        )
    text = result.response.choices[0].message.content
    if not isinstance(text, str):
        text = json.dumps(text)
    return MCPToolResponse(content=[MCPContent(type="text", text=text)])


@router.post("/mcp/tools/providers_status", response_model=MCPToolResponse)
async def mcp_providers_status() -> MCPToolResponse:
    statuses = await get_router().get_provider_statuses()
    text = json.dumps([s.model_dump() for s in statuses])
    return MCPToolResponse(content=[MCPContent(type="text", text=text)])
