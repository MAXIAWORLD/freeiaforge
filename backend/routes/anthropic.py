from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.models import ChatRequest, Message
from routes.chat import get_router

logger = logging.getLogger(__name__)
router = APIRouter()

_KNOWN_PROVIDERS = frozenset(
    {
        "cerebras",
        "groq",
        "sambanova",
        "gemini",
        "huggingface",
        "mistral",
        "openrouter",
        "ollama",
    }
)

_FINISH_REASON_MAP = {"stop": "end_turn", "length": "max_tokens"}


# ---------------------------------------------------------------------------
# Anthropic request / response models
# ---------------------------------------------------------------------------


class AnthropicMessage(BaseModel):
    role: str
    content: str | list[dict]


class AnthropicRequest(BaseModel):
    model: str
    messages: list[AnthropicMessage]
    max_tokens: int = Field(default=1024, gt=0)
    system: str | None = None
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    stream: bool = False


class AnthropicTextBlock(BaseModel):
    type: str = "text"
    text: str


class AnthropicUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class AnthropicResponse(BaseModel):
    id: str
    type: str = "message"
    role: str = "assistant"
    model: str
    content: list[AnthropicTextBlock]
    stop_reason: str
    usage: AnthropicUsage


class AnthropicError(BaseModel):
    type: str = "error"
    error: dict


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def _error_response(status: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "error", "error": {"type": error_type, "message": message}},
    )


@router.post("/v1/messages")
async def anthropic_messages(body: AnthropicRequest, response: Response):
    if body.stream:
        return _error_response(
            400, "invalid_request_error", "Streaming not supported. Set stream=false."
        )

    # Build internal message list
    msgs: list[Message] = []
    if body.system:
        msgs.append(Message(role="system", content=body.system))
    for m in body.messages:
        msgs.append(Message(role=m.role, content=m.content))  # type: ignore[arg-type]

    # Model hint: use if known provider, else "auto"
    model_hint = body.model.lower()
    if model_hint not in _KNOWN_PROVIDERS:
        model_hint = "auto"

    internal = ChatRequest(
        model=model_hint,
        messages=msgs,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
    )

    try:
        result = await get_router().route(internal)
    except (HTTPException, RuntimeError) as exc:
        status = exc.status_code if isinstance(exc, HTTPException) else 529
        msg = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return _error_response(status, "overloaded_error", str(msg))

    choice = result.response.choices[0]
    text = choice.message.content
    if not isinstance(text, str):
        text = json.dumps(text)

    stop_reason = _FINISH_REASON_MAP.get(choice.finish_reason, "end_turn")

    logger.info(
        "Anthropic endpoint served by %s (%d tokens)",
        result.provider_name,
        result.tokens_used,
    )

    response.headers["X-Provider"] = result.provider_name
    return AnthropicResponse(
        id=f"msg_{result.response.id}",
        model=result.response.model,
        content=[AnthropicTextBlock(type="text", text=text)],
        stop_reason=stop_reason,
        usage=AnthropicUsage(
            input_tokens=result.response.usage.prompt_tokens,
            output_tokens=result.response.usage.completion_tokens,
        ),
    )
