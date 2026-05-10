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

    async def discover_default_model(self, api_key: str) -> str:
        """Return the default model id, optionally refreshed from the provider's
        live model list. Default impl keeps the hardcoded value; subclasses that
        expose a /models endpoint override this."""
        return getattr(self, "default_model", "")

    async def validate_key(self, api_key: str) -> bool:
        """Return True if the api_key is accepted by the provider.

        Default implementation assumes the key is valid (used by providers
        without auth such as Ollama). OpenAI-compatible providers override
        this with a lightweight GET /models probe.
        """
        return True


class OpenAICompatibleProvider(Provider):
    """Base for providers exposing OpenAI-compatible /v1/chat/completions."""

    base_url: str
    default_model: str

    async def validate_key(self, api_key: str) -> bool:  # type: ignore[override]
        """Probe ``GET {base_url}/models`` with the key.

        - 2xx → key is valid (or at least usable).
        - 401/403 → key is rejected — caller should put it on cooldown.
        - Anything else (5xx, network error, timeout) is treated as a
          provider-side issue and the key is left untouched.
        """
        if not api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
        except httpx.HTTPError:
            return True  # transient: don't punish the key
        if r.status_code in (401, 403):
            return False
        return True

    async def discover_default_model(self, api_key: str) -> str:
        if not api_key:
            return self.default_model
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                r.raise_for_status()
                payload = r.json()
        except (httpx.HTTPError, ValueError):
            return self.default_model

        if not isinstance(payload, dict):
            return self.default_model
        raw = payload.get("data") or payload.get("models") or []
        models: list[str] = []
        for entry in raw:
            if isinstance(entry, dict):
                model_id = entry.get("id") or entry.get("name") or ""
                if isinstance(model_id, str) and model_id:
                    models.append(model_id)
            elif isinstance(entry, str):
                models.append(entry)
        if not models:
            return self.default_model
        return self._select_best_model(models)

    def _select_best_model(self, models: list[str]) -> str:
        """Select the best model for chat. Default: keep hardcoded if still
        listed, otherwise pick the first available."""
        if self.default_model in models:
            return self.default_model
        return models[0]

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
