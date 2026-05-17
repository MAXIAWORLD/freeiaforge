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
from services.task_inference import (
    infer_task_type,
    TASK_LONG_CONTEXT,
    TASK_VISION,
    TASK_CODE,
    has_vision,
    total_chars,
)

if TYPE_CHECKING:
    import aiosqlite
    from services.cache import ExactCache, SemanticCache
    from services.stats_history import record_request as _record_request_type

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
        "nvidia_nim",
        "cloudflare",
        "ollama",
    }
)

# Seuil de caractères au-delà duquel Cerebras est skipé (redondant avec task_inference, conservé en défense)
_CEREBRAS_CHAR_LIMIT = 24_000

_MULTIMODAL_PROVIDERS = frozenset({"gemini", "openrouter"})
_CODE_PRIORITY_PROVIDERS = frozenset({"groq", "cerebras"})

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
        cache: "ExactCache | SemanticCache | None" = None,
        provider_order: list[str] | None = None,
        credential_pool: CredentialPool | None = None,
        db: "aiosqlite.Connection | None" = None,
        cb_failure_threshold: int = 3,
        cb_timeout_seconds: int = 600,
        cb_half_open_after: int = 300,
        stats_db: "aiosqlite.Connection | None" = None,
    ) -> None:
        self._use_static_order = bool(provider_order)
        if provider_order:
            self._providers = self._apply_order(providers, provider_order)
        else:
            self._providers = sorted(providers, key=lambda p: p.priority)
        self._quota = quota
        self._api_keys = api_keys or {}
        self._cache = cache
        self._error_state: dict[str, dict] = {}
        self._db = db
        self._cb_failure_threshold = cb_failure_threshold
        self._cb_timeout_seconds = cb_timeout_seconds
        self._cb_half_open_after = cb_half_open_after
        self._daily_stats: dict[str, int] = {}
        self._daily_date: str = ""
        self._total_today: int = 0
        self._stats_db = stats_db

        # Build credential pool from api_keys if no explicit pool was provided.
        if credential_pool is None:
            credential_pool = CredentialPool()
            for name, key in self._api_keys.items():
                if key:
                    credential_pool.add_keys(name, [key])
        self._pool = credential_pool

    async def _key_for(self, provider_name: str) -> str:
        """Resolve the active API key for ``provider_name`` via the pool."""
        return await self._pool.next_key(provider_name) or ""

    async def restore_circuit_state(self) -> None:
        """Load persisted circuit_state rows into in-memory _error_state."""
        if self._db is None:
            return
        async with self._db.execute(
            "SELECT provider, consecutive_errors, last_error, last_used_at, "
            "circuit_status, open_since FROM circuit_state"
        ) as cursor:
            rows = await cursor.fetchall()
        for provider, consecutive_errors, last_error, last_used_at, circuit_status, open_since in rows:
            self._error_state[provider] = {
                "consecutive_errors": consecutive_errors,
                "last_error": last_error,
                "last_used_at": last_used_at,
                "circuit_status": circuit_status or "CLOSED",
                "open_since": open_since,
            }

    async def _persist_circuit_state(self, provider_name: str) -> None:
        if self._db is None:
            return
        state = self._error_state.get(provider_name, {})
        await self._db.execute(
            """
            INSERT INTO circuit_state
                (provider, consecutive_errors, last_error, last_used_at,
                 circuit_status, open_since)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET
                consecutive_errors = excluded.consecutive_errors,
                last_error = excluded.last_error,
                last_used_at = excluded.last_used_at,
                circuit_status = excluded.circuit_status,
                open_since = excluded.open_since
            """,
            (
                provider_name,
                state.get("consecutive_errors", 0),
                state.get("last_error"),
                state.get("last_used_at"),
                state.get("circuit_status", "CLOSED"),
                state.get("open_since"),
            ),
        )
        await self._db.commit()

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

    def get_daily_stats(self) -> dict:
        today = datetime.now(tz=timezone.utc).date().isoformat()
        if self._daily_date != today:
            return {"total": 0, "by_task": {}}
        return {"total": self._total_today, "by_task": dict(self._daily_stats)}

    def _record_daily(self, task_type: str) -> None:
        today = datetime.now(tz=timezone.utc).date().isoformat()
        if self._daily_date != today:
            self._daily_date = today
            self._daily_stats = {}
            self._total_today = 0
        self._total_today += 1
        self._daily_stats[task_type] = self._daily_stats.get(task_type, 0) + 1

    # ------------------------------------------------------------------
    # Circuit Breaker — machine à états
    # ------------------------------------------------------------------

    def _get_circuit_status(self, provider_name: str) -> str:
        return self._error_state.get(provider_name, {}).get("circuit_status", "CLOSED")

    def _is_circuit_available(self, provider_name: str) -> bool:
        """True si le provider peut recevoir une requête (CLOSED ou probe HALF_OPEN)."""
        status = self._get_circuit_status(provider_name)
        if status == "CLOSED":
            return True
        if status == "HALF_OPEN":
            return True
        # OPEN — vérifier si le délai de récupération est écoulé
        state = self._error_state.get(provider_name, {})
        open_since_str = state.get("open_since")
        if not open_since_str:
            return False
        try:
            open_since = datetime.fromisoformat(open_since_str)
            elapsed = (datetime.now(tz=timezone.utc) - open_since).total_seconds()
            if elapsed >= self._cb_half_open_after:
                state["circuit_status"] = "HALF_OPEN"
                logger.info("[%s] Circuit OPEN → HALF_OPEN (probe autorisé)", provider_name)
                return True
        except (ValueError, TypeError):
            pass
        return False

    async def _on_success(self, provider_name: str) -> None:
        state = self._error_state.setdefault(provider_name, {})
        was_recovering = state.get("circuit_status") in ("HALF_OPEN", "OPEN")
        state["consecutive_errors"] = 0
        state["last_used_at"] = self._now_iso()
        state.setdefault("last_error", None)
        state["circuit_status"] = "CLOSED"
        state["open_since"] = None
        if was_recovering:
            logger.info("[%s] Circuit → CLOSED (rétabli)", provider_name)
        await self._persist_circuit_state(provider_name)

    async def _on_error(self, provider_name: str, error: ProviderError) -> None:
        # 400 = erreur requête user, 401 = clé invalide (géré par le pool)
        if error.status_code in (400, 401):
            return
        state = self._error_state.setdefault(provider_name, {})
        state["consecutive_errors"] = state.get("consecutive_errors", 0) + 1
        state["last_error"] = str(error)
        state.setdefault("last_used_at", None)
        current_status = state.get("circuit_status", "CLOSED")
        if current_status == "HALF_OPEN" or state["consecutive_errors"] >= self._cb_failure_threshold:
            state["circuit_status"] = "OPEN"
            state["open_since"] = self._now_iso()
            logger.warning(
                "[%s] Circuit → OPEN (errors=%d)", provider_name, state["consecutive_errors"]
            )
        await self._persist_circuit_state(provider_name)

    # ------------------------------------------------------------------
    # Tri dynamique par quota restant
    # ------------------------------------------------------------------

    async def _providers_by_quota(self) -> list[Provider]:
        """Trie les providers par ratio quota restant décroissant.

        Si un ordre explicite a été configuré (provider_order), l'ordre statique
        est respecté sans re-tri. Tiebreak : priority (ascendant).
        """
        if self._use_static_order:
            return list(self._providers)
        ratios: dict[str, float] = {}
        for p in self._providers:
            try:
                status = await self._quota.get_status(p.name)
                lim = status.requests_limit
                ratios[p.name] = (lim - status.requests_used) / lim if lim > 0 else 1.0
            except Exception:
                ratios[p.name] = 1.0
        return sorted(
            self._providers,
            key=lambda p: (-ratios.get(p.name, 1.0), p.priority),
        )

    def _should_skip(self, provider_name: str, request: ChatRequest) -> bool:
        """Règle de sécurité : Cerebras skipé si contexte > CEREBRAS_CHAR_LIMIT.

        La vision et le long_context sont désormais gérés par _providers_for_task
        avant l'entrée dans la boucle.
        """
        if (
            provider_name == "cerebras"
            and total_chars(request) > _CEREBRAS_CHAR_LIMIT
        ):
            logger.debug("Skipping cerebras: context > %d chars", _CEREBRAS_CHAR_LIMIT)
            return True
        return False

    def _providers_for_task(
        self, task_type: str, providers: list[Provider]
    ) -> list[Provider]:
        """Filtre/réordonne les providers selon le type de tâche inféré."""
        if task_type == TASK_LONG_CONTEXT:
            gemini_only = [p for p in providers if p.name == "gemini"]
            return gemini_only if gemini_only else providers
        if task_type == TASK_VISION:
            multimodal = [p for p in providers if p.name in _MULTIMODAL_PROVIDERS]
            return multimodal if multimodal else providers
        if task_type == TASK_CODE:
            priority = [p for p in providers if p.name in _CODE_PRIORITY_PROVIDERS]
            rest = [p for p in providers if p.name not in _CODE_PRIORITY_PROVIDERS]
            return priority + rest
        return providers

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

        # Inférer le type de tâche + filtrer/réordonner les providers
        task_type = infer_task_type(request)
        ordered = await self._providers_by_quota()
        ordered = self._providers_for_task(task_type, ordered)

        for provider in ordered:
            key = await self._key_for(provider.name)
            if not key:
                logger.debug("Skipping %s: no API key available", provider.name)
                continue
            if not await self._quota.is_available(provider.name):
                logger.info("Skipping %s: quota exhausted", provider.name)
                continue
            if not self._is_circuit_available(provider.name):
                logger.debug("Skipping %s: circuit %s", provider.name, self._get_circuit_status(provider.name))
                continue
            if self._should_skip(provider.name, request):
                continue
            try:
                result = await provider.complete(request, key)
                await self._quota.record_usage(
                    provider.name, requests=1, tokens=result.tokens_used
                )
                await self._on_success(provider.name)
                await self._pool.mark_success(provider.name, key)
                self._record_daily(task_type)
                if self._stats_db is not None:
                    from services.stats_history import record_request
                    await record_request(self._stats_db, task_type, provider.name, result.tokens_used)
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
                await self._on_error(provider.name, e)
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
            await self._on_success(hint)
            await self._pool.mark_success(hint, key)
            logger.info("Served by %s (hinted, %d tokens)", hint, result.tokens_used)
            return result
        except ProviderError as e:
            await self._on_error(hint, e)
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
            await self._on_success(hint)
            await self._pool.mark_success(hint, key)
            return hint, _safe_stream(hint, target.stream(request, key))

        task_type = infer_task_type(request)
        ordered = await self._providers_by_quota()
        ordered = self._providers_for_task(task_type, ordered)

        for provider in ordered:
            key = await self._key_for(provider.name)
            if not key:
                continue
            if not await self._quota.is_available(provider.name):
                continue
            if not self._is_circuit_available(provider.name):
                continue
            if self._should_skip(provider.name, request):
                continue
            await self._quota.record_usage(provider.name, requests=1, tokens=0)
            await self._on_success(provider.name)
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
                    circuit_status=state.get("circuit_status", "CLOSED"),
                )
            )
        return statuses
