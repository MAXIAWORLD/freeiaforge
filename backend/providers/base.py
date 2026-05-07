from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
import httpx
from core.models import ChatRequest, ChatResponse


class ProviderError(Exception):
    def __init__(
        self, provider: str, status_code: int | None = None, reason: str = ""
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.reason = reason
        msg = f"Provider '{provider}' error"
        if status_code:
            msg += f" (HTTP {status_code})"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


@dataclass(frozen=True)
class ProviderResult:
    response: ChatResponse
    provider_name: str
    tokens_used: int


class Provider(ABC):
    name: str
    priority: int

    @abstractmethod
    async def complete(self, request: ChatRequest, api_key: str) -> ProviderResult: ...

    async def stream(  # type: ignore[return]
        self, request: ChatRequest, api_key: str
    ) -> AsyncIterator[str]:
        raise NotImplementedError(f"{self.name} does not support streaming")
        yield  # pragma: no cover — makes this an async generator


class OpenAICompatibleProvider(Provider):
    """Base for providers exposing OpenAI-compatible /v1/chat/completions."""

    base_url: str
    default_model: str

    async def complete(self, request: ChatRequest, api_key: str) -> ProviderResult:
        payload: dict = {
            "model": self.default_model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(self.name, status_code=e.response.status_code) from e
        except httpx.RequestError as e:
            raise ProviderError(
                self.name, reason=f"network error: {type(e).__name__}"
            ) from e

        try:
            response = ChatResponse(
                id=data["id"],
                model=data["model"],
                choices=[
                    {
                        "index": c["index"],
                        "message": c["message"],
                        "finish_reason": c.get("finish_reason", "stop"),
                    }
                    for c in data["choices"]
                ],
                usage=data["usage"],
            )
            tokens_used = data["usage"]["total_tokens"]
        except (KeyError, ValueError) as e:
            raise ProviderError(self.name, reason="malformed response") from e

        return ProviderResult(
            response=response,
            provider_name=self.name,
            tokens_used=tokens_used,
        )

    async def stream(  # type: ignore[override]
        self, request: ChatRequest, api_key: str
    ) -> AsyncIterator[str]:
        payload: dict = {
            "model": self.default_model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as r:
                    try:
                        r.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        raise ProviderError(
                            self.name, status_code=e.response.status_code
                        ) from e
                    async for line in r.aiter_lines():
                        if line:
                            yield line + "\n\n"
        except httpx.RequestError as e:
            raise ProviderError(
                self.name, reason=f"network error: {type(e).__name__}"
            ) from e
