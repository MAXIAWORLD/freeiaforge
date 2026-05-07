from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import aiosqlite

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.database import close_db, init_db
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
from services.quota import QuotaService
from services.router import ProviderRouter

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

    set_router(
        ProviderRouter(
            providers=providers,
            quota=quota,
            api_keys=api_keys,
            cache=cache,
            provider_order=provider_order,
        )
    )

    # Ollama sentinel "local" doesn't count as an external key
    active = sum(1 for k, v in api_keys.items() if v and k != "ollama")
    logger.info(
        "FreeIA Gateway ready — %d/%d cloud providers active",
        active,
        len(providers) - 1,
    )
    yield
    await close_db(db)


app = FastAPI(title="FreeIA Gateway", version="0.5.0", lifespan=lifespan)
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
