"""
Tests TDD — Phase 6 : historique 7 jours dans dashboard + /v1/quota.

Cas couverts :
  - GET /v1/quota retourne une clé "history" (liste)
  - "history" est [] quand _stats_db est None
  - "history" contient les données de get_last_7_days quand stats_db est dispo
  - Dashboard HTML affiche une section "Last 7 days"
  - Dashboard HTML affiche les colonnes de l'historique (day, provider, requests)
  - Dashboard HTML affiche "no data" quand historique vide
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_HISTORY = [
    {"day": "2026-05-17", "task_type": "default", "provider": "cerebras", "requests": 42, "tokens": 10000},
    {"day": "2026-05-16", "task_type": "code",    "provider": "groq",     "requests": 7,  "tokens": 2500},
]


def _mock_router_with_history(history: list) -> AsyncMock:
    from core.models import ProviderStatus
    mock_router = AsyncMock()
    mock_router.get_provider_statuses = AsyncMock(return_value=[
        ProviderStatus(
            name="cerebras", available=True,
            requests_used=42, requests_limit=1000,
            tokens_used=10000, tokens_limit=1_000_000,
        )
    ])
    mock_router.get_daily_stats = MagicMock(return_value={"total": 42, "by_task": {"default": 42}})
    mock_router._providers = [MagicMock()]
    mock_router._stats_db = MagicMock()  # non-None sentinel
    return mock_router


# ---------------------------------------------------------------------------
# GET /v1/quota — clé "history"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quota_has_history_key():
    from main import app

    with patch("routes.health.get_router") as mock_get, \
         patch("routes.health.get_last_7_days", new_callable=AsyncMock) as mock_hist:
        mock_hist.return_value = _SAMPLE_HISTORY
        mock_get.return_value = _mock_router_with_history(_SAMPLE_HISTORY)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/quota")

    assert r.status_code == 200
    assert "history" in r.json()


@pytest.mark.asyncio
async def test_quota_history_is_list():
    from main import app

    with patch("routes.health.get_router") as mock_get, \
         patch("routes.health.get_last_7_days", new_callable=AsyncMock) as mock_hist:
        mock_hist.return_value = _SAMPLE_HISTORY
        mock_get.return_value = _mock_router_with_history(_SAMPLE_HISTORY)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/quota")

    assert isinstance(r.json()["history"], list)


@pytest.mark.asyncio
async def test_quota_history_contains_expected_data():
    from main import app

    with patch("routes.health.get_router") as mock_get, \
         patch("routes.health.get_last_7_days", new_callable=AsyncMock) as mock_hist:
        mock_hist.return_value = _SAMPLE_HISTORY
        mock_get.return_value = _mock_router_with_history(_SAMPLE_HISTORY)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/quota")

    history = r.json()["history"]
    assert len(history) == 2
    assert history[0]["day"] == "2026-05-17"
    assert history[0]["provider"] == "cerebras"
    assert history[0]["requests"] == 42


@pytest.mark.asyncio
async def test_quota_history_empty_when_no_stats_db():
    """Quand _stats_db est None, history doit être []."""
    from main import app

    with patch("routes.health.get_router") as mock_get:
        mock_router = AsyncMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=[])
        mock_router.get_daily_stats = MagicMock(return_value={"total": 0, "by_task": {}})
        mock_router._providers = []
        mock_router._stats_db = None
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/quota")

    assert r.json()["history"] == []


# ---------------------------------------------------------------------------
# Dashboard HTML — section "Last 7 days"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_shows_last_7_days_heading():
    from main import app

    with patch("routes.dashboard.get_router") as mock_get, \
         patch("routes.dashboard.get_last_7_days", new_callable=AsyncMock) as mock_hist:
        mock_hist.return_value = _SAMPLE_HISTORY
        mock_get.return_value = _mock_router_with_history(_SAMPLE_HISTORY)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/")

    assert "Last 7 days" in r.text


@pytest.mark.asyncio
async def test_dashboard_shows_history_provider():
    from main import app

    with patch("routes.dashboard.get_router") as mock_get, \
         patch("routes.dashboard.get_last_7_days", new_callable=AsyncMock) as mock_hist:
        mock_hist.return_value = _SAMPLE_HISTORY
        mock_get.return_value = _mock_router_with_history(_SAMPLE_HISTORY)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/")

    assert "2026-05-17" in r.text


@pytest.mark.asyncio
async def test_dashboard_history_empty_shows_no_data():
    from main import app

    with patch("routes.dashboard.get_router") as mock_get, \
         patch("routes.dashboard.get_last_7_days", new_callable=AsyncMock) as mock_hist:
        mock_hist.return_value = []
        router = _mock_router_with_history([])
        router._stats_db = None
        mock_get.return_value = router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/")

    assert "no data" in r.text
