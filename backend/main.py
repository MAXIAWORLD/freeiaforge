from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

import aiosqlite
import httpx

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
from providers.sambanova import SambanovaProvider
from routes.chat import router as chat_router
from routes.chat import set_memory, set_router
from services.memory import MemPalaceService
from routes.health import router as health_router
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
    }
    quota = QuotaService(db=db, limits=limits)

    api_keys = {
        "cerebras": settings.cerebras_api_key,
        "groq": settings.groq_api_key,
        "sambanova": settings.sambanova_api_key,
        "gemini": settings.gemini_api_key,
        "huggingface": settings.huggingface_api_key,
        "mistral": settings.mistral_api_key,
    }
    providers = [
        CerebrasProvider(),
        GroqProvider(),
        SambanovaProvider(),
        GeminiProvider(),
        HuggingFaceProvider(),
        MistralProvider(),
    ]
    set_router(ProviderRouter(providers=providers, quota=quota, api_keys=api_keys))

    memory = MemPalaceService(Path("/app/data"))
    set_memory(memory)

    _flag = Path("/app/data/.installed")
    if not _flag.exists():
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post("https://maxiaworld.app/counter/freeai")
            _flag.touch()
        except Exception:
            pass

    active = sum(1 for v in api_keys.values() if v)
    logger.info("FreeIA Gateway ready — %d/%d providers active", active, len(providers))
    yield
    await close_db(db)


app = FastAPI(title="FreeIA Gateway", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(chat_router)
app.include_router(health_router)
