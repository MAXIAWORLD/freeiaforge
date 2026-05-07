from __future__ import annotations

import httpx

from core.models import ChatRequest, ChatResponse
from providers.base import OpenAICompatibleProvider, ProviderError, ProviderResult

_HTTP_REFERER = "https://maxiaworld.app"
_X_TITLE = "FreeIA Gateway"


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter free-tier router — priority 7 (last-resort fallback).

    OpenRouter requires two extra headers on every request:
      - HTTP-Referer: identifies the calling app
      - X-Title: human-readable app name shown in OpenRouter dashboard
    """

    name = "openrouter"
    priority = 7
    base_url = "https://openrouter.ai/api/v1"
    default_model = "openrouter/free"

    async def complete(self, request: ChatRequest, api_key: str) -> ProviderResult:
        payload: dict = {
            "model": self.default_model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": _HTTP_REFERER,
            "X-Title": _X_TITLE,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
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
