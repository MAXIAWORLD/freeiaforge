from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class Message(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    role: Literal["system", "user", "assistant"]
    content: str | list[dict]  # str pour texte, list[dict] pour contenu multimodal


class ChatRequest(BaseModel):
    model: str = "auto"
    messages: list[Message]
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    stream: bool = False


class ChatChoice(BaseModel):
    index: int
    message: Message
    finish_reason: str


class ChatUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    model: str
    choices: list[ChatChoice]
    usage: ChatUsage


class ProviderStatus(BaseModel):
    name: str
    available: bool
    requests_used: int
    requests_limit: int
    tokens_used: int
    tokens_limit: int
    last_error: str | None = None
    last_used_at: str | None = None
    consecutive_errors: int = 0
    circuit_status: str = "CLOSED"
