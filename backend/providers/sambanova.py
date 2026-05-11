from __future__ import annotations

import httpx

from providers.base import OpenAICompatibleProvider, ProviderError, ProviderResult
from core.models import ChatRequest, ChatResponse

_GATEWAY_ALIASES = frozenset({"auto", "freeai-gateway"})


class SambanovaProvider(OpenAICompatibleProvider):
    name = "sambanova"
    priority = 3
    base_url = "https://api.sambanova.ai/v1"
    default_model = "Meta-Llama-3.3-70B-Instruct"

    SUPPORTED_MODELS: frozenset[str] = frozenset(
        {
            "Meta-Llama-3.3-70B-Instruct",
            "Llama-3.1-405B-Instruct",
            "Qwen2.5-72B-Instruct",
        }
    )

    def _resolve_model(self, requested: str) -> str:
        """Retourne le modèle à transmettre à l'API Sambanova.

        - alias gateway (auto, freeai-gateway) → default_model
        - modèle dans SUPPORTED_MODELS → transmis tel quel
        - inconnu → default_model
        """
        if requested in _GATEWAY_ALIASES:
            return self.default_model
        if requested in self.SUPPORTED_MODELS:
            return requested
        return self.default_model

    async def complete(self, request: ChatRequest, api_key: str) -> ProviderResult:
        model = self._resolve_model(request.model)

        payload: dict = {
            "model": model,
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
