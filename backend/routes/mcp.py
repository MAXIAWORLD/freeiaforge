from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.models import ChatRequest, Message
from routes.chat import get_router

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# MCP Streamable HTTP — JSON-RPC 2.0 (spec 2025-03-26)
# ---------------------------------------------------------------------------

_PROTOCOL_VERSION = "2025-03-26"
_SERVER_NAME = "freeai-gateway"
_SERVER_VERSION = "0.8.0"

_TOOLS: list[dict] = [
    {
        "name": "chat",
        "description": (
            "Send messages to the best available free LLM. "
            "Auto-fallback across 9 cloud providers + Ollama."
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
                        "gemini, huggingface, mistral, openrouter, nvidia_nim, cloudflare, ollama"
                    ),
                },
            },
            "required": ["messages"],
        },
    },
    {
        "name": "providers_status",
        "description": "Get status of all LLM providers (quota remaining, errors, availability).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

# Legacy manifest — GET /mcp kept for backward compatibility
_MANIFEST: dict = {
    "name": _SERVER_NAME,
    "version": _SERVER_VERSION,
    "description": "10 LLMs (9 cloud + Ollama) behind one OpenAI-compatible API",
    "tools": _TOOLS,
}


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 helpers
# ---------------------------------------------------------------------------


def _ok(result: Any, req_id: Any) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "result": result, "id": req_id})


def _err(code: int, message: str, req_id: Any) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id}
    )


# ---------------------------------------------------------------------------
# Method handlers
# ---------------------------------------------------------------------------


async def _handle_initialize(params: dict, req_id: Any) -> JSONResponse:
    return _ok(
        {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
        },
        req_id,
    )


async def _handle_tools_list(params: dict, req_id: Any) -> JSONResponse:
    return _ok({"tools": _TOOLS}, req_id)


async def _handle_tools_call(params: dict, req_id: Any) -> JSONResponse:
    name = params.get("name", "")
    arguments: dict = params.get("arguments") or {}

    if name == "chat":
        messages = [Message(**m) for m in arguments.get("messages", [])]
        model = arguments.get("model", "auto")
        request = ChatRequest(model=model, messages=messages)
        try:
            result = await get_router().route(request)
        except Exception as exc:
            return _ok({"content": [{"type": "text", "text": f"[error] {exc}"}]}, req_id)
        text = result.response.choices[0].message.content
        if not isinstance(text, str):
            text = json.dumps(text)
        return _ok({"content": [{"type": "text", "text": text}]}, req_id)

    if name == "providers_status":
        statuses = await get_router().get_provider_statuses()
        text = json.dumps([s.model_dump() for s in statuses])
        return _ok({"content": [{"type": "text", "text": text}]}, req_id)

    return _err(-32602, f"Unknown tool: {name}", req_id)


_DISPATCH = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/mcp")
async def mcp_manifest() -> dict:
    return _MANIFEST


@router.post("/mcp")
async def mcp_jsonrpc(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return _err(-32700, "Parse error", None)

    req_id = body.get("id")
    method = body.get("method", "")
    params: dict = body.get("params") or {}

    if body.get("jsonrpc") != "2.0":
        return _err(-32600, "Invalid Request: jsonrpc must be '2.0'", req_id)

    handler = _DISPATCH.get(method)
    if handler is None:
        return _err(-32601, "Method not found", req_id)

    return await handler(params, req_id)
