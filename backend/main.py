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
from providers.cloudflare import CloudflareProvider
from providers.gemini import GeminiProvider
from providers.groq import GroqProvider
from providers.huggingface import HuggingFaceProvider
from providers.mistral import MistralProvider
from providers.nvidia_nim import NvidiaProvider
from providers.ollama import OllamaProvider
from providers.openrouter import OpenRouterProvider
from providers.sambanova import SambanovaProvider
from middleware.auth import GatewayAuthMiddleware
from routes.anthropic import router as anthropic_router
from routes.chat import router as chat_router
from routes.chat import set_router
from routes.dashboard import router as dashboard_router
from routes.health import router as health_router
from routes.mcp import router as mcp_router
from services.cache import ExactCache, SemanticCache
from services.credential_pool import CredentialPool
from services.key_validator import validate_keys
from services.providers_config import apply_providers_config, fetch_providers_config
from services.quota import QuotaService
from services.router import ProviderRouter
from services.stats_history import init_stats_db
from services.stats_reporter import report_startup
from services.version_check import check_version


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
    data_dir = os.path.dirname(settings.db_path) or "."
    os.makedirs(data_dir, exist_ok=True)
    db = await aiosqlite.connect(settings.db_path)
    await init_db(db)
    stats_db = await aiosqlite.connect(settings.stats_db_path)
    await init_stats_db(stats_db)

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
        "nvidia_nim": {
            "requests": settings.nvidia_nim_daily_requests,
            "tokens": settings.nvidia_nim_daily_tokens,
        },
        "cloudflare": {
            "requests": settings.cloudflare_daily_requests,
            "tokens": settings.cloudflare_daily_tokens,
        },
        "ollama": {
            "requests": settings.ollama_daily_requests,
            "tokens": settings.ollama_daily_tokens,
        },
    }
    # providers.json : fetch remote overrides (non-bloquant si échec)
    from pathlib import Path
    providers_data = await fetch_providers_config(
        url=settings.providers_json_url,
        local_path=Path(settings.db_path).parent / "providers.json",
    )
    if providers_data:
        limits = apply_providers_config(limits, providers_data)

    quota = QuotaService(db=db, limits=limits)

    api_keys = {
        "cerebras": settings.cerebras_api_key,
        "groq": settings.groq_api_key,
        "sambanova": settings.sambanova_api_key,
        "gemini": settings.gemini_api_key,
        "huggingface": settings.huggingface_api_key,
        "mistral": settings.mistral_api_key,
        "openrouter": settings.openrouter_api_key,
        "nvidia_nim": settings.nvidia_nim_api_key,
        "cloudflare": settings.cloudflare_api_token,
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
    pool.add_keys(
        "nvidia_nim", _parse_keys("NVIDIA_NIM_API_KEYS", settings.nvidia_nim_api_key)
    )
    pool.add_keys(
        "cloudflare",
        _parse_keys("CLOUDFLARE_API_TOKENS", settings.cloudflare_api_token),
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
    ]
    if settings.cloudflare_account_id:
        providers.append(CloudflareProvider(account_id=settings.cloudflare_account_id))
    providers.append(NvidiaProvider())
    providers.append(
        OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
    )

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
    cache: ExactCache | SemanticCache | None = None
    if settings.cache_enabled:
        from pathlib import Path
        data_dir = Path(settings.db_path).parent
        try:
            import fastembed  # noqa: F401
            cache = SemanticCache(
                data_dir=data_dir,
                similarity_threshold=settings.cache_similarity_threshold,
            )
            logger.info(
                "SemanticCache enabled (threshold=%.2f, TTL=%ds)",
                settings.cache_similarity_threshold,
                settings.cache_ttl_seconds,
            )
        except ImportError:
            cache = ExactCache(data_dir=data_dir)
            logger.info("ExactCache enabled (fastembed absent, TTL=%ds)", settings.cache_ttl_seconds)

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
        cb_failure_threshold=settings.cb_failure_threshold,
        cb_timeout_seconds=settings.cb_timeout_seconds,
        cb_half_open_after=settings.cb_half_open_after,
        stats_db=stats_db,
    )
    await router_instance.restore_circuit_state()
    set_router(router_instance)

    _log_startup_banner(providers, api_keys, key_stats, settings)

    has_ollama = any(p.name == "ollama" for p in providers)
    await asyncio.gather(
        check_version(app.version),
        report_startup(
            version=app.version,
            providers_count=len(providers),
            has_ollama=has_ollama,
        ),
        return_exceptions=True,
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
        await close_db(stats_db)


def _log_startup_banner(
    providers: list,
    api_keys: dict,
    key_stats: dict,
    settings,
) -> None:
    _QUOTA_LABELS: dict[str, str] = {
        "cerebras": "1M tok/j · 30 RPM",
        "groq": "14 400 req/j · 30 RPM",
        "sambanova": "1 000 req/j",
        "gemini": "1 500 req/j · 1M ctx",
        "huggingface": "1 000 req/j",
        "mistral": "reserve · 2 RPM",
        "openrouter": ":free models",
        "nvidia_nim": "40 RPM · 100+ models",
        "cloudflare": "10 000 req/j",
        "ollama": "∞ local",
    }
    lines = [f"\nFreeIA Gateway v{app.version}", "=" * 52]
    for p in providers:
        key = api_keys.get(p.name, "")
        if p.name == "ollama":
            icon = "✅"
            note = f"local ({settings.ollama_base_url})"
        elif key and key != "local":
            invalid = key_stats.get(p.name, {}).get("invalid", 0)
            icon = "⚠️ " if invalid else "✅"
            note = _QUOTA_LABELS.get(p.name, "")
        else:
            icon = "❌"
            note = "no key — skipped"
        label = _QUOTA_LABELS.get(p.name, "")
        logger.info("  %-14s %s  %s", p.name, icon, note or label)
    lines.append("=" * 52)
    logger.info(
        "\nFreeIA Gateway v%s\n%s\nRouting: quota-aware + circuit breaker\nReady → http://0.0.0.0:8002",
        app.version,
        "\n".join(
            f"  {p.name:<14} {'✅' if (api_keys.get(p.name) and api_keys[p.name] != 'local') or p.name == 'ollama' else '❌'}  {_QUOTA_LABELS.get(p.name, '')}"
            for p in providers
        ),
    )


app = FastAPI(title="FreeIA Gateway", version="0.8.0", lifespan=lifespan)
app.add_middleware(
    GatewayAuthMiddleware,
    api_key=os.environ.get("FREEAI_API_KEY", ""),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(dashboard_router)
app.include_router(chat_router)
app.include_router(anthropic_router)
app.include_router(health_router)
app.include_router(mcp_router)
