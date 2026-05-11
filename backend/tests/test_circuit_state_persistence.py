"""TDD — circuit_state SQLite persistence (Phase A jour 3, freeiaforge v0.6.0)

The router's _error_state (consecutive_errors, last_error, last_used_at) used
to live in RAM only and got wiped on every restart. We now persist it through
the same aiosqlite connection that backs quota/credential_pool tables.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.models import (
    ChatChoice,
    ChatRequest,
    ChatResponse,
    ChatUsage,
    Message,
    ProviderStatus,
)
from providers.base import ProviderError, ProviderResult
from services.router import ProviderRouter


def _make_result(provider_name: str) -> ProviderResult:
    return ProviderResult(
        response=ChatResponse(
            id="x",
            model="m",
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role="assistant", content="ok"),
                    finish_reason="stop",
                )
            ],
            usage=ChatUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
        provider_name=provider_name,
        tokens_used=2,
    )


def _make_request() -> ChatRequest:
    return ChatRequest(messages=[Message(role="user", content="hi")])


def _mock_quota_ok() -> AsyncMock:
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    async def _status(provider_name: str) -> ProviderStatus:
        return ProviderStatus(
            name=provider_name,
            available=True,
            requests_used=0,
            requests_limit=1000,
            tokens_used=0,
            tokens_limit=1_000_000,
        )

    quota.get_status = AsyncMock(side_effect=_status)
    return quota


# ---------------------------------------------------------------------------
# Persistence on error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_persists_consecutive_errors_on_provider_error(pool_db):
    """_on_error must persist consecutive_errors=1 and last_error to SQLite."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 2
    p1.complete = AsyncMock(side_effect=ProviderError("groq", status_code=503))

    p2 = AsyncMock()
    p2.name = "ollama"
    p2.priority = 9
    p2.complete = AsyncMock(return_value=_make_result("ollama"))

    router = ProviderRouter(
        providers=[p1, p2],
        quota=_mock_quota_ok(),
        api_keys={"groq": "k", "ollama": "local"},
        db=pool_db,
    )
    await router.route(_make_request())

    async with pool_db.execute(
        "SELECT consecutive_errors, last_error FROM circuit_state WHERE provider='groq'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] is not None and "503" in row[1]


@pytest.mark.asyncio
async def test_router_increments_consecutive_errors_across_calls(pool_db):
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 2
    p1.complete = AsyncMock(side_effect=ProviderError("groq", status_code=500))

    p2 = AsyncMock()
    p2.name = "ollama"
    p2.priority = 9
    p2.complete = AsyncMock(return_value=_make_result("ollama"))

    router = ProviderRouter(
        providers=[p1, p2],
        quota=_mock_quota_ok(),
        api_keys={"groq": "k", "ollama": "local"},
        db=pool_db,
    )
    await router.route(_make_request())
    await router.route(_make_request())
    await router.route(_make_request())

    async with pool_db.execute(
        "SELECT consecutive_errors FROM circuit_state WHERE provider='groq'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row[0] == 3


# ---------------------------------------------------------------------------
# Reset on success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_resets_consecutive_errors_on_success(pool_db):
    """_on_success must zero out consecutive_errors and refresh last_used_at."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 2
    p1.complete = AsyncMock(return_value=_make_result("groq"))

    router = ProviderRouter(
        providers=[p1],
        quota=_mock_quota_ok(),
        api_keys={"groq": "k"},
        db=pool_db,
    )

    # Pre-populate the table with a stale failure
    await pool_db.execute(
        "INSERT INTO circuit_state (provider, consecutive_errors, last_error, last_used_at) "
        "VALUES ('groq', 5, 'old failure', '2024-01-01T00:00:00+00:00')"
    )
    await pool_db.commit()

    await router.route(_make_request())

    async with pool_db.execute(
        "SELECT consecutive_errors, last_used_at FROM circuit_state WHERE provider='groq'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row[0] == 0
    assert row[1] is not None and "2024" not in row[1]


# ---------------------------------------------------------------------------
# Restore at boot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_restores_circuit_state_from_db(pool_db):
    """A new router instance must inherit _error_state from the persisted table."""
    await pool_db.execute(
        "INSERT INTO circuit_state (provider, consecutive_errors, last_error, last_used_at) "
        "VALUES ('groq', 7, 'HTTP 503', '2026-05-10T12:00:00+00:00')"
    )
    await pool_db.commit()

    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 2

    router = ProviderRouter(
        providers=[p1],
        quota=_mock_quota_ok(),
        api_keys={"groq": "k"},
        db=pool_db,
    )
    await router.restore_circuit_state()

    statuses = await router.get_provider_statuses()
    groq_status = next(s for s in statuses if s.name == "groq")
    assert groq_status.consecutive_errors == 7
    assert groq_status.last_error == "HTTP 503"


# ---------------------------------------------------------------------------
# Backward compat — no db
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_without_db_keeps_in_memory_only():
    """Existing tests that don't pass a db must keep working unchanged."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 2
    p1.complete = AsyncMock(side_effect=ProviderError("groq", status_code=500))

    p2 = AsyncMock()
    p2.name = "ollama"
    p2.priority = 9
    p2.complete = AsyncMock(return_value=_make_result("ollama"))

    router = ProviderRouter(
        providers=[p1, p2],
        quota=_mock_quota_ok(),
        api_keys={"groq": "k", "ollama": "local"},
    )
    await router.route(_make_request())

    statuses = await router.get_provider_statuses()
    groq_status = next(s for s in statuses if s.name == "groq")
    assert groq_status.consecutive_errors == 1
    # restore_circuit_state must be a safe no-op without a db
    await router.restore_circuit_state()
