import pytest_asyncio
import aiosqlite
from core.database import init_db, close_db
from services.quota import QuotaService

TEST_LIMITS = {
    "cerebras": {"requests": 5000, "tokens": 1_000_000},
    "groq": {"requests": 2, "tokens": 500_000},  # low for testing
    "sambanova": {"requests": 1000, "tokens": 1_000_000},
    "gemini": {"requests": 1500, "tokens": 1_000_000},
    "huggingface": {"requests": 1000, "tokens": 500_000},
    "mistral": {"requests": 100, "tokens": 200_000},
}


@pytest_asyncio.fixture
async def quota(tmp_path):
    db_path = str(tmp_path / "test.db")
    db = await aiosqlite.connect(db_path)
    await init_db(db)
    service = QuotaService(db=db, limits=TEST_LIMITS)
    yield service
    await close_db(db)
