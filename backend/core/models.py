from __future__ import annotations
from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "auto"
    messages: list[Message]
    temperature: float = 0.7
    max_tokens: int | None = None
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
