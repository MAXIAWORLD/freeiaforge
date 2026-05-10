from __future__ import annotations
import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException
from core.models import ChatRequest, ProviderStatus
from providers.base import Provider, ProviderResult, ProviderError
from services.credential_pool import CredentialPool
from services.quota import QuotaService

if TYPE_CHECKING:
    from services.cache import SemanticCache

logger = logging.getLogger(__name__)

# Providers connus pour le model hint (Règle 3)
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

# Seuil de caractères au-delà duquel Cerebras est skipé (≈8000 tokens × 3 chars/token)
_CEREBRAS_CHAR_LIMIT = 24_000

# TTL par défaut pour le cache (en secondes)
_DEFAULT_CACHE_TTL = 3600


_DONE_CHUNK = "data: [DONE]\n\n"


async def _safe_stream(
    provider_name: str, inner: AsyncIterator[str]
) -> AsyncIterator[str]:
    """Wrap a provider stream so that:

    - The SSE termination ``data: [DONE]\\n\\n`` is always emitted exactly once.
    - ``ProviderError`` and unexpected exceptions are converted into an OpenAI-style
      error chunk + ``[DONE]`` instead of propagating (which would close the
      response brutally and trigger 'Premature close' on AnythingLLM/LibreChat).
    """
    done_seen = False
    try:
        async for line in inner:
            if "[DONE]" in line:
                done_seen = True
            yield line
    except ProviderError as exc:
        payload = {
            "error": {
                "message": str(exc),
                "type": "provider_error",
                "provider": provider_name,
                "code": exc.status_code,
            }
        }
        yield f"data: {json.dumps(payload)}\n\n"
        logger.warning(
            "Stream from %s raised ProviderError: %s", provider_name, exc
        )
    except Exception as exc:  # pragma: no cover — defensive
        payload = {
            "error": {
                "message": f"unexpected: {type(exc).__name__}: {exc}",
                "type": "internal_error",
                "provider": provider_name,
            }
        }
        yield f"data: {json.dumps(payload)}\n\n"
        logger.exception("Stream from %s raised unexpected exception", provider_name)
    finally:
        if not done_seen:
            yield _DONE_CHUNK


class ProviderRouter:
    def __init__(
        self,
        providers: list[Provider],
        quota: QuotaService,
        api_keys: dict[str, str] | None = None,
        cache: SemanticCache | None = None,
        provider_order: list[str] | None = None,
        credential_pool: CredentialPool | None = None,
    ) -> None:
        if provider_order:
            self._providers = self._apply_order(providers, provider_order)
        else:
            self._providers = sorted(providers, key=lambda p: p.priority)
        self._quota = quota
        self._api_keys = api_keys or {}
        self._cache = cache
        # State d'erreur in-memory : {provider_name: {consecutive_errors, last_error, last_used_at}}
        self._error_state: dict[str, dict] = {}

        # Build credential pool from api_keys if no explicit pool was provided.
        # When an explicit pool is given, it overrides api_keys for key resolution
        # but api_keys remains exposed for legacy /v1/models discovery.
        if credential_pool is None:
            credential_pool = CredentialPool()
            for name, key in self._api_keys.items():
                if key:
                    credential_pool.add_keys(name, [key])
        self._pool = credential_pool

    async def _key_for(self, provider_name: str) -> str:
        """Resolve the active API key for ``provider_name`` via the pool."""
        return await self._pool.next_key(provider_name) or ""

    async def refresh_default_models(self) -> None:
        """Query each configured provider's /models endpoint and update its
        default_model accordingly. Failures are non-fatal (keep hardcoded)."""

        async def _refresh(provider: Provider) -> None:
            api_key = self._api_keys.get(provider.name, "")
            if not api_key:
                return
            previous = getattr(provider, "default_model", "")
            try:
                fresh = await provider.discover_default_model(api_key)
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning(
                    "[%s] discover_default_model failed: %s", provider.name, exc
                )
                return
            if fresh and fresh != previous:
                logger.info(
                    "[%s] default_model: %s → %s", provider.name, previous, fresh
                )
                provider.default_model = fresh  # type: ignore[attr-defined]

        await asyncio.gather(
            *(_refresh(p) for p in self._providers), return_exceptions=True
        )

    @staticmethod
    def _apply_order(providers: list[Provider], order: list[str]) -> list[Provider]:
        by_name = {p.name: p for p in providers}
        ordered = [by_name[name] for name in order if name in by_name]
        ordered_names = {p.name for p in ordered}
        rest = sorted(
            [p for p in providers if p.name not in ordered_names],
            key=lambda p: p.priority,
        )
        return ordered + rest

    # ------------------------------------------------------------------
    # Helpers internes
    # ------------------------------------------------------------------

    def _now_iso(self) -> str:
        return datetime.now(tz=timezone.utc).isoformat()

    def _on_success(self, provider_name: str) -> None:
        state = self._error_state.setdefault(provider_name, {})
        state["consecutive_errors"] = 0
        state["last_used_at"] = self._now_iso()

    def _on_error(self, provider_name: str, error: ProviderError) -> None:
        state = self._error_state.setdefault(provider_name, {})
        state["consecutive_errors"] = state.get("consecutive_errors", 0) + 1
        state["last_error"] = str(error)
        state.setdefault("last_used_at", None)

    def _has_vision(self, request: ChatRequest) -> bool:
        """Détecte si l'un des messages contient une image (content multimodal)."""
        for msg in request.messages:
            if isinstance(msg.content, list):
                for part in msg.content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        return True
        return False

    def _total_chars(self, request: ChatRequest) -> int:
        total = 0
        for msg in request.messages:
            if isinstance(msg.content, str):
                total += len(msg.content)
            elif isinstance(msg.content, list):
                for part in msg.content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += len(part.get("text", ""))
        return total

    def _should_skip(self, provider_name: str, request: ChatRequest) -> bool:
        """
        Règle 1 : Cerebras skipé si contexte > 24 000 chars.
        Règle 2 : Vision → seul Gemini autorisé.
        (La règle 3 model-hint est gérée séparément dans route().)
        """
        # Règle 2 — vision
        if self._has_vision(request) and provider_name != "gemini":
            logger.debug("Skipping %s: vision request requires Gemini", provider_name)
            return True

        # Règle 1 — contexte long pour Cerebras
        if (
            provider_name == "cerebras"
            and self._total_chars(request) > _CEREBRAS_CHAR_LIMIT
        ):
            logger.debug("Skipping cerebras: context > %d chars", _CEREBRAS_CHAR_LIMIT)
            return True

        return False

    # ------------------------------------------------------------------
    # Routing principal
    # ------------------------------------------------------------------

    async def route(self, request: ChatRequest) -> ProviderResult:
        # Cache lookup — avant tout appel provider
        if self._cache is not None:
            cached = await self._cache.lookup(request.messages)
            if cached is not None:
                logger.info("Cache hit — skipping providers")
                return ProviderResult(
                    response=cached, provider_name="cache", tokens_used=0
                )

        # Règle 3 — model hint explicite
        hint = request.model.lower() if request.model else "auto"
        if hint in _KNOWN_PROVIDERS:
            return await self._route_hinted(request, hint)

        # Routing normal avec règles de skip
        for provider in self._providers:
            key = await self._key_for(provider.name)
            if not key:
                logger.debug("Skipping %s: no API key available", provider.name)
                continue
            if not await self._quota.is_available(provider.name):
                logger.info("Skipping %s: quota exhausted", provider.name)
                continue
            if self._should_skip(provider.name, request):
                continue
            try:
                result = await provider.complete(request, key)
                await self._quota.record_usage(
                    provider.name, requests=1, tokens=result.tokens_used
                )
                self._on_success(provider.name)
                await self._pool.mark_success(provider.name, key)
                logger.info(
                    "Served by %s (%d tokens)", provider.name, result.tokens_used
                )
                # Cache store — fire-and-forget
                if self._cache is not None:
                    asyncio.create_task(
                        self._cache.store(
                            request.messages,
                            result.response,
                            ttl_seconds=_DEFAULT_CACHE_TTL,
                        )
                    )
                return result
            except ProviderError as e:
                self._on_error(provider.name, e)
                await self._pool.mark_failure(provider.name, key, e.status_code)
                logger.warning("Provider %s failed (%s), trying next", provider.name, e)
                continue

        raise RuntimeError("All providers exhausted")

    async def _route_hinted(self, request: ChatRequest, hint: str) -> ProviderResult:
        """Tente uniquement le provider ciblé par le model hint."""
        # Trouver le provider dans la liste
        target = next((p for p in self._providers if p.name == hint), None)
        key = await self._key_for(hint)

        if not key or target is None:
            raise HTTPException(
                status_code=503,
                detail=f"Provider '{hint}' is not available: no API key configured",
            )
        if not await self._quota.is_available(hint):
            raise HTTPException(
                status_code=503,
                detail=f"Provider '{hint}' is not available: quota exhausted",
            )
        try:
            result = await target.complete(request, key)
            await self._quota.record_usage(hint, requests=1, tokens=result.tokens_used)
            self._on_success(hint)
            await self._pool.mark_success(hint, key)
            logger.info("Served by %s (hinted, %d tokens)", hint, result.tokens_used)
            return result
        except ProviderError as e:
            self._on_error(hint, e)
            await self._pool.mark_failure(hint, key, e.status_code)
            raise HTTPException(
                status_code=503,
                detail=f"Provider '{hint}' failed: {e}",
            )

    # ------------------------------------------------------------------
    # Streaming route
    # ------------------------------------------------------------------

    async def route_stream(
        self, request: ChatRequest
    ) -> tuple[str, AsyncIterator[str]]:
        """Returns (provider_name, sse_stream) for the first available provider."""
        hint = request.model.lower() if request.model else "auto"

        if hint in _KNOWN_PROVIDERS:
            target = next((p for p in self._providers if p.name == hint), None)
            key = await self._key_for(hint)
            if not key or target is None:
                raise RuntimeError(
                    f"Provider '{hint}' not available: no API key configured"
                )
            if not await self._quota.is_available(hint):
                raise RuntimeError(f"Provider '{hint}' not available: quota exhausted")
            await self._quota.record_usage(hint, requests=1, tokens=0)
            self._on_success(hint)
            await self._pool.mark_success(hint, key)
            return hint, _safe_stream(hint, target.stream(request, key))

        for provider in self._providers:
            key = await self._key_for(provider.name)
            if not key:
                continue
            if not await self._quota.is_available(provider.name):
                continue
            if self._should_skip(provider.name, request):
                continue
            await self._quota.record_usage(provider.name, requests=1, tokens=0)
            self._on_success(provider.name)
            await self._pool.mark_success(provider.name, key)
            return provider.name, _safe_stream(
                provider.name, provider.stream(request, key)
            )

        raise RuntimeError("All providers exhausted")

    # ------------------------------------------------------------------
    # Status enrichi
    # ------------------------------------------------------------------

    async def get_provider_statuses(self) -> list[ProviderStatus]:
        statuses = []
        for p in self._providers:
            base = await self._quota.get_status(p.name)
            state = self._error_state.get(p.name, {})
            statuses.append(
                ProviderStatus(
                    name=base.name,
                    available=base.available,
                    requests_used=base.requests_used,
                    requests_limit=base.requests_limit,
                    tokens_used=base.tokens_used,
                    tokens_limit=base.tokens_limit,
                    last_error=state.get("last_error"),
                    last_used_at=state.get("last_used_at"),
                    consecutive_errors=state.get("consecutive_errors", 0),
                )
            )
        return statuses
