from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import aiosqlite

# Refresh provider default_model from each provider's /models endpoint at
# startup, then every 24h while the server runs.
_MODEL_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.database import close_db, init_db
from core.logging_config import configure_logging

configure_logging(log_dir=os.environ.get("FREEAIGATE_LOG_DIR", "data/logs"))
from providers.cerebras import CerebrasProvider
from providers.gemini import GeminiProvider
from providers.groq import GroqProvider
from providers.huggingface import HuggingFaceProvider
from providers.mistral import MistralProvider
from providers.ollama import OllamaProvider
from providers.openrouter import OpenRouterProvider
from providers.sambanova import SambanovaProvider
from routes.anthropic import router as anthropic_router
from routes.chat import router as chat_router
from routes.chat import set_router
from routes.health import router as health_router
from routes.mcp import router as mcp_router
from services.cache import SemanticCache
from services.credential_pool import CredentialPool
from services.key_validator import validate_keys
from services.quota import QuotaService
from services.router import ProviderRouter


def _parse_keys(env_plural: str, single_fallback: str) -> list[str]:
    """Parse `XXX_API_KEYS=k1,k2,k3` if set, else fall back to single `XXX_API_KEY`.

    Returns an empty list when nothing is configured. Whitespace and empty
    entries are stripped so users can paste comma-separated keys without
    fearing typos like `,,key1,, key2`.
    """
    raw = os.getenv(env_plural, "")
    if raw:
        return [k.strip() for k in raw.split(",") if k.strip()]
    return [single_fallback] if single_fallback else []

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    db = await aiosqlite.connect(settings.db_path)
    await init_db(db)

    limits = {
        "cerebras": {
            "requests": settings.cerebras_daily_requests,
            "tokens": settings.cerebras_daily_tokens,
        },
        "groq": {
            "requests": settings.groq_daily_requests,
            "tokens": settings.groq_daily_tokens,
        },
        "sambanova": {
            "requests": settings.sambanova_daily_requests,
            "tokens": settings.sambanova_daily_tokens,
        },
        "gemini": {
            "requests": settings.gemini_daily_requests,
            "tokens": settings.gemini_daily_tokens,
        },
        "huggingface": {
            "requests": settings.huggingface_daily_requests,
            "tokens": settings.huggingface_daily_tokens,
        },
        "mistral": {
            "requests": settings.mistral_daily_requests,
            "tokens": settings.mistral_daily_tokens,
        },
        "openrouter": {
            "requests": settings.openrouter_daily_requests,
            "tokens": settings.openrouter_daily_tokens,
        },
        "ollama": {
            "requests": settings.ollama_daily_requests,
            "tokens": settings.ollama_daily_tokens,
        },
    }
    quota = QuotaService(db=db, limits=limits)

    api_keys = {
        "cerebras": settings.cerebras_api_key,
        "groq": settings.groq_api_key,
        "sambanova": settings.sambanova_api_key,
        "gemini": settings.gemini_api_key,
        "huggingface": settings.huggingface_api_key,
        "mistral": settings.mistral_api_key,
        "openrouter": settings.openrouter_api_key,
        "ollama": "local",  # sentinel — Ollama needs no auth
    }

    # Multi-key credential pool: prefer XXX_API_KEYS=k1,k2,k3 when set, else
    # fall back to legacy XXX_API_KEY single-key form. Pool rotates and applies
    # a 24h cooldown on 401/402/429 (key-level errors) per provider. State is
    # persisted in SQLite so cooldowns survive restarts.
    pool = CredentialPool(db=db)
    pool.add_keys(
        "cerebras", _parse_keys("CEREBRAS_API_KEYS", settings.cerebras_api_key)
    )
    pool.add_keys("groq", _parse_keys("GROQ_API_KEYS", settings.groq_api_key))
    pool.add_keys(
        "sambanova", _parse_keys("SAMBANOVA_API_KEYS", settings.sambanova_api_key)
    )
    pool.add_keys("gemini", _parse_keys("GEMINI_API_KEYS", settings.gemini_api_key))
    pool.add_keys(
        "huggingface",
        _parse_keys("HUGGINGFACE_API_KEYS", settings.huggingface_api_key),
    )
    pool.add_keys("mistral", _parse_keys("MISTRAL_API_KEYS", settings.mistral_api_key))
    pool.add_keys(
        "openrouter", _parse_keys("OPENROUTER_API_KEYS", settings.openrouter_api_key)
    )
    pool.add_keys("ollama", ["local"])
    await pool.restore()
    providers = [
        CerebrasProvider(),
        GroqProvider(),
        SambanovaProvider(),
        GeminiProvider(),
        HuggingFaceProvider(),
        MistralProvider(),
        OpenRouterProvider(),
        OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model),
    ]

    # Probe each configured key once so 401/403 keys land on cooldown before
    # any user request hits them. 5xx/network errors leave keys untouched.
    key_stats = await validate_keys(providers, pool)
    for provider_name, counts in key_stats.items():
        if counts.get("invalid", 0):
            logger.warning(
                "[%s] %d/%d api_keys rejected at startup",
                provider_name,
                counts["invalid"],
                counts["valid"] + counts["invalid"],
            )
    cache: SemanticCache | None = None
    if settings.cache_enabled:
        from pathlib import Path

        cache = SemanticCache(data_dir=Path(settings.db_path).parent)
        logger.info("Semantic cache enabled (TTL=%ds)", settings.cache_ttl_seconds)

    provider_order = (
        [x.strip() for x in settings.provider_order.split(",") if x.strip()]
        if settings.provider_order
        else None
    )

    router_instance = ProviderRouter(
        providers=providers,
        quota=quota,
        api_keys=api_keys,
        cache=cache,
        provider_order=provider_order,
        credential_pool=pool,
        db=db,
    )
    await router_instance.restore_circuit_state()
    set_router(router_instance)

    # Ollama sentinel "local" doesn't count as an external key
    active = sum(1 for k, v in api_keys.items() if v and k != "ollama")
    logger.info(
        "freeaigate ready — %d/%d cloud providers active",
        active,
        len(providers) - 1,
    )

    await router_instance.refresh_default_models()

    async def _periodic_refresh() -> None:
        while True:
            await asyncio.sleep(_MODEL_REFRESH_INTERVAL_SECONDS)
            try:
                await router_instance.refresh_default_models()
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning("Periodic model refresh failed: %s", exc)

    refresh_task = asyncio.create_task(_periodic_refresh())
    try:
        yield
    finally:
        refresh_task.cancel()
        try:
            await refresh_task
        except (asyncio.CancelledError, Exception):
            pass
        await close_db(db)


app = FastAPI(title="freeaigate", version="0.6.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(chat_router)
app.include_router(anthropic_router)
app.include_router(health_router)
app.include_router(mcp_router)
