"""
Tests TDD — Phase 5 : SQLite séparé + stats_history.

Cas couverts :
  config :
    - db_path par défaut pointe vers quota.db
    - stats_db_path par défaut pointe vers stats.db
  cache :
    - ExactCache crée cache.db, pas freeai.db
  stats_history :
    - init_stats_db crée la table request_log + index ts
    - record_request insère une ligne
    - get_last_7_days retourne agrégats par jour/task_type
    - get_last_7_days exclut données > 7 jours
    - get_last_7_days retourne [] si vide
  router intégration :
    - route() avec stats_db enregistre une entrée dans request_log
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from core.models import (
    ChatChoice, ChatRequest, ChatResponse, ChatUsage, Message, ProviderStatus,
)
from providers.base import ProviderResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(name: str) -> ProviderResult:
    return ProviderResult(
        response=ChatResponse(
            id="x", model="m",
            choices=[ChatChoice(index=0, message=Message(role="assistant", content="ok"), finish_reason="stop")],
            usage=ChatUsage(prompt_tokens=1, completion_tokens=5, total_tokens=6),
        ),
        provider_name=name,
        tokens_used=6,
    )


def _mock_quota_ok() -> AsyncMock:
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()
    async def _status(name: str) -> ProviderStatus:
        return ProviderStatus(
            name=name, available=True,
            requests_used=0, requests_limit=1000,
            tokens_used=0, tokens_limit=1_000_000,
        )
    quota.get_status = AsyncMock(side_effect=_status)
    return quota


# ---------------------------------------------------------------------------
# Config — chemins par défaut
# ---------------------------------------------------------------------------

def test_config_db_path_default_is_quota_db():
    from core.config import Settings
    s = Settings()
    assert "quota.db" in s.db_path


def test_config_has_stats_db_path():
    from core.config import Settings
    s = Settings()
    assert hasattr(s, "stats_db_path")
    assert "stats.db" in s.stats_db_path


def test_config_stats_db_path_same_dir_as_quota(tmp_path):
    """stats_db_path et db_path sont dans le même répertoire."""
    from core.config import Settings
    s = Settings()
    assert Path(s.db_path).parent == Path(s.stats_db_path).parent


# ---------------------------------------------------------------------------
# Cache — fichier séparé
# ---------------------------------------------------------------------------

def test_cache_uses_cache_db_not_freeai_db(tmp_path):
    from services.cache import ExactCache
    cache = ExactCache(data_dir=tmp_path)
    assert cache._db_path.name == "cache.db"
    assert "freeai" not in cache._db_path.name


@pytest.mark.asyncio
async def test_cache_creates_cache_db_file(tmp_path):
    from services.cache import ExactCache
    from core.models import Message
    cache = ExactCache(data_dir=tmp_path)
    # trigger initialization
    result = await cache.lookup([Message(role="user", content="test")])
    assert result is None
    assert (tmp_path / "cache.db").exists()
    assert not (tmp_path / "freeai.db").exists()


# ---------------------------------------------------------------------------
# stats_history — init + record + query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_init_stats_db_creates_request_log_table():
    from services.stats_history import init_stats_db
    async with aiosqlite.connect(":memory:") as db:
        await init_stats_db(db)
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='request_log'"
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_init_stats_db_creates_ts_index():
    from services.stats_history import init_stats_db
    async with aiosqlite.connect(":memory:") as db:
        await init_stats_db(db)
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_ts'"
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_record_request_inserts_row():
    from services.stats_history import init_stats_db, record_request, get_last_7_days
    async with aiosqlite.connect(":memory:") as db:
        await init_stats_db(db)
        await record_request(db, task_type="code", provider="groq", tokens_used=42)
        rows = await get_last_7_days(db)
    assert len(rows) == 1
    assert rows[0]["task_type"] == "code"
    assert rows[0]["provider"] == "groq"
    assert rows[0]["tokens"] == 42
    assert rows[0]["requests"] == 1


@pytest.mark.asyncio
async def test_get_last_7_days_groups_by_day_and_task():
    from services.stats_history import init_stats_db, record_request, get_last_7_days
    async with aiosqlite.connect(":memory:") as db:
        await init_stats_db(db)
        await record_request(db, "code", "groq", 10)
        await record_request(db, "code", "groq", 20)
        await record_request(db, "default", "cerebras", 5)
        rows = await get_last_7_days(db)

    by_task = {r["task_type"]: r for r in rows}
    assert by_task["code"]["requests"] == 2
    assert by_task["code"]["tokens"] == 30
    assert by_task["default"]["requests"] == 1
    assert by_task["default"]["tokens"] == 5


@pytest.mark.asyncio
async def test_get_last_7_days_excludes_old_data():
    from services.stats_history import init_stats_db, get_last_7_days
    old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=8)).isoformat()
    async with aiosqlite.connect(":memory:") as db:
        await init_stats_db(db)
        await db.execute(
            "INSERT INTO request_log (ts, task_type, provider, tokens_used) VALUES (?, ?, ?, ?)",
            (old_ts, "default", "groq", 100),
        )
        await db.commit()
        rows = await get_last_7_days(db)
    assert rows == []


@pytest.mark.asyncio
async def test_get_last_7_days_empty_returns_empty_list():
    from services.stats_history import init_stats_db, get_last_7_days
    async with aiosqlite.connect(":memory:") as db:
        await init_stats_db(db)
        rows = await get_last_7_days(db)
    assert rows == []


@pytest.mark.asyncio
async def test_record_request_stores_ts():
    from services.stats_history import init_stats_db, record_request
    async with aiosqlite.connect(":memory:") as db:
        await init_stats_db(db)
        await record_request(db, "vision", "gemini", 0)
        async with db.execute("SELECT ts FROM request_log") as cursor:
            row = await cursor.fetchone()
    assert row is not None
    ts = row[0]
    # ISO-8601 format
    datetime.fromisoformat(ts)


# ---------------------------------------------------------------------------
# Router — persiste dans stats_db après route()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_records_to_stats_db_on_success():
    from services.router import ProviderRouter
    from services.stats_history import init_stats_db, get_last_7_days

    quota = _mock_quota_ok()
    p = AsyncMock()
    p.name = "cerebras"
    p.priority = 1
    p.complete = AsyncMock(return_value=_make_result("cerebras"))

    async with aiosqlite.connect(":memory:") as stats_db:
        await init_stats_db(stats_db)
        router = ProviderRouter(
            providers=[p],
            quota=quota,
            api_keys={"cerebras": "key"},
            stats_db=stats_db,
        )
        req = ChatRequest(messages=[Message(role="user", content="bonjour")])
        await router.route(req)
        rows = await get_last_7_days(stats_db)

    assert len(rows) == 1
    assert rows[0]["task_type"] == "default"
    assert rows[0]["provider"] == "cerebras"
    assert rows[0]["tokens"] == 6


@pytest.mark.asyncio
async def test_router_without_stats_db_still_works():
    """stats_db est optionnel — route() fonctionne sans."""
    from services.router import ProviderRouter

    quota = _mock_quota_ok()
    p = AsyncMock()
    p.name = "cerebras"
    p.priority = 1
    p.complete = AsyncMock(return_value=_make_result("cerebras"))

    router = ProviderRouter(
        providers=[p],
        quota=quota,
        api_keys={"cerebras": "key"},
    )
    req = ChatRequest(messages=[Message(role="user", content="hello")])
    result = await router.route(req)
    assert result.provider_name == "cerebras"
