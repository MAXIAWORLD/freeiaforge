"""
Tests TDD — Phase 3 : Dashboard + quota endpoint + health enrichi.

Cas couverts :
  - ProviderStatus.circuit_status champ présent avec défaut "CLOSED"
  - router.get_daily_stats() retourne zéro avant toute requête
  - router.get_daily_stats() s'incrémente après route() réussie
  - GET /health retourne version + providers count
  - GET /v1/quota retourne providers + daily_stats
  - GET /v1/quota expose circuit_status de chaque provider
  - GET / retourne HTML (content-type text/html)
  - GET / affiche les noms des providers
  - GET / affiche les valeurs de circuit_status (OPEN/CLOSED)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
            usage=ChatUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
        provider_name=name,
        tokens_used=2,
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


def _mock_status(name: str, circuit_status: str = "CLOSED") -> ProviderStatus:
    return ProviderStatus(
        name=name, available=True,
        requests_used=100, requests_limit=1000,
        tokens_used=5000, tokens_limit=1_000_000,
        circuit_status=circuit_status,
    )


# ---------------------------------------------------------------------------
# ProviderStatus — champ circuit_status
# ---------------------------------------------------------------------------

def test_provider_status_has_circuit_status_default_closed():
    ps = ProviderStatus(
        name="cerebras", available=True,
        requests_used=0, requests_limit=1000,
        tokens_used=0, tokens_limit=1_000_000,
    )
    assert ps.circuit_status == "CLOSED"


def test_provider_status_circuit_status_can_be_open():
    ps = ProviderStatus(
        name="groq", available=False,
        requests_used=1000, requests_limit=1000,
        tokens_used=0, tokens_limit=1_000_000,
        circuit_status="OPEN",
    )
    assert ps.circuit_status == "OPEN"


def test_provider_status_circuit_status_half_open():
    ps = ProviderStatus(
        name="gemini", available=True,
        requests_used=0, requests_limit=1000,
        tokens_used=0, tokens_limit=1_000_000,
        circuit_status="HALF_OPEN",
    )
    assert ps.circuit_status == "HALF_OPEN"


# ---------------------------------------------------------------------------
# Daily stats dans ProviderRouter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_daily_stats_initial_zero():
    from services.router import ProviderRouter
    router = ProviderRouter(providers=[], quota=AsyncMock(), api_keys={})
    stats = router.get_daily_stats()
    assert stats["total"] == 0
    assert stats["by_task"] == {}


@pytest.mark.asyncio
async def test_router_daily_stats_increments_on_route():
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
    req = ChatRequest(messages=[Message(role="user", content="bonjour")])
    await router.route(req)

    stats = router.get_daily_stats()
    assert stats["total"] == 1
    assert stats["by_task"].get("default", 0) == 1


@pytest.mark.asyncio
async def test_router_daily_stats_tracks_task_types():
    from services.router import ProviderRouter

    quota = _mock_quota_ok()
    p = AsyncMock()
    p.name = "groq"
    p.priority = 1
    p.complete = AsyncMock(return_value=_make_result("groq"))

    router = ProviderRouter(
        providers=[p],
        quota=quota,
        api_keys={"groq": "key"},
    )
    # code request
    code_req = ChatRequest(messages=[Message(role="user", content="fix this:\n```python\npass\n```")])
    await router.route(code_req)
    # default request
    default_req = ChatRequest(messages=[Message(role="user", content="hello")])
    await router.route(default_req)

    stats = router.get_daily_stats()
    assert stats["total"] == 2
    assert stats["by_task"]["code"] == 1
    assert stats["by_task"]["default"] == 1


# ---------------------------------------------------------------------------
# get_provider_statuses() retourne circuit_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_provider_statuses_includes_circuit_status():
    from services.router import ProviderRouter

    quota = _mock_quota_ok()
    p = AsyncMock()
    p.name = "cerebras"
    p.priority = 1

    router = ProviderRouter(
        providers=[p],
        quota=quota,
        api_keys={"cerebras": "key"},
    )
    # Simuler circuit OPEN
    router._error_state["cerebras"] = {
        "consecutive_errors": 3,
        "last_error": "timeout",
        "last_used_at": None,
        "circuit_status": "OPEN",
        "open_since": "2026-05-17T10:00:00+00:00",
    }

    statuses = await router.get_provider_statuses()
    assert len(statuses) == 1
    assert statuses[0].circuit_status == "OPEN"


# ---------------------------------------------------------------------------
# GET /health enrichi
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_includes_version():
    from main import app

    with patch("routes.health.get_router") as mock_get:
        mock_router = MagicMock()
        mock_router._providers = [MagicMock(), MagicMock(), MagicMock()]
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/health")

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert isinstance(data["version"], str)


@pytest.mark.asyncio
async def test_health_includes_providers_count():
    from main import app

    with patch("routes.health.get_router") as mock_get:
        mock_router = MagicMock()
        mock_router._providers = [MagicMock(), MagicMock(), MagicMock()]
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/health")

    data = r.json()
    assert data["providers"] == 3


@pytest.mark.asyncio
async def test_health_works_without_router():
    """GET /health doit retourner 200 même si le router n'est pas encore initialisé."""
    from main import app

    with patch("routes.health.get_router", side_effect=RuntimeError("not init")):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/health")

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["providers"] == 0


# ---------------------------------------------------------------------------
# GET /v1/quota
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quota_endpoint_returns_200():
    from main import app

    with patch("routes.health.get_router") as mock_get:
        mock_router = AsyncMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=[
            _mock_status("cerebras"),
            _mock_status("groq", "OPEN"),
        ])
        mock_router.get_daily_stats = MagicMock(return_value={"total": 42, "by_task": {"default": 30, "code": 12}})
        mock_router._providers = [MagicMock(), MagicMock()]
        mock_router._stats_db = None
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/quota")

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_quota_endpoint_has_providers_and_daily_stats():
    from main import app

    with patch("routes.health.get_router") as mock_get:
        mock_router = AsyncMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=[
            _mock_status("cerebras"),
        ])
        mock_router.get_daily_stats = MagicMock(return_value={"total": 5, "by_task": {"default": 5}})
        mock_router._providers = [MagicMock()]
        mock_router._stats_db = None
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/quota")

    data = r.json()
    assert "providers" in data
    assert "daily_stats" in data
    assert isinstance(data["providers"], list)


@pytest.mark.asyncio
async def test_quota_exposes_circuit_status():
    from main import app

    with patch("routes.health.get_router") as mock_get:
        mock_router = AsyncMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=[
            _mock_status("cerebras", "CLOSED"),
            _mock_status("groq", "OPEN"),
        ])
        mock_router.get_daily_stats = MagicMock(return_value={"total": 0, "by_task": {}})
        mock_router._providers = [MagicMock(), MagicMock()]
        mock_router._stats_db = None
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/quota")

    data = r.json()
    by_name = {p["name"]: p for p in data["providers"]}
    assert by_name["cerebras"]["circuit_status"] == "CLOSED"
    assert by_name["groq"]["circuit_status"] == "OPEN"


@pytest.mark.asyncio
async def test_quota_daily_stats_values():
    from main import app

    with patch("routes.health.get_router") as mock_get:
        mock_router = AsyncMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=[])
        mock_router.get_daily_stats = MagicMock(
            return_value={"total": 10, "by_task": {"code": 7, "vision": 3}}
        )
        mock_router._providers = []
        mock_router._stats_db = None
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/quota")

    data = r.json()
    assert data["daily_stats"]["total"] == 10
    assert data["daily_stats"]["by_task"]["code"] == 7
    assert data["daily_stats"]["by_task"]["vision"] == 3


# ---------------------------------------------------------------------------
# GET / — Dashboard HTML
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_returns_html_content_type():
    from main import app

    with patch("routes.dashboard.get_router") as mock_get:
        mock_router = AsyncMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=[
            _mock_status("cerebras"),
        ])
        mock_router.get_daily_stats = MagicMock(return_value={"total": 0, "by_task": {}})
        mock_router._providers = [MagicMock()]
        mock_router._stats_db = None
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/")

    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_dashboard_shows_provider_names():
    from main import app

    with patch("routes.dashboard.get_router") as mock_get:
        mock_router = AsyncMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=[
            _mock_status("cerebras"),
            _mock_status("groq"),
        ])
        mock_router.get_daily_stats = MagicMock(return_value={"total": 0, "by_task": {}})
        mock_router._providers = [MagicMock(), MagicMock()]
        mock_router._stats_db = None
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/")

    assert "cerebras" in r.text
    assert "groq" in r.text


@pytest.mark.asyncio
async def test_dashboard_shows_circuit_open():
    from main import app

    with patch("routes.dashboard.get_router") as mock_get:
        mock_router = AsyncMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=[
            _mock_status("gemini", "OPEN"),
        ])
        mock_router.get_daily_stats = MagicMock(return_value={"total": 0, "by_task": {}})
        mock_router._providers = [MagicMock()]
        mock_router._stats_db = None
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/")

    assert "OPEN" in r.text


@pytest.mark.asyncio
async def test_dashboard_shows_freeai_branding():
    from main import app

    with patch("routes.dashboard.get_router") as mock_get:
        mock_router = AsyncMock()
        mock_router.get_provider_statuses = AsyncMock(return_value=[])
        mock_router.get_daily_stats = MagicMock(return_value={"total": 0, "by_task": {}})
        mock_router._providers = []
        mock_router._stats_db = None
        mock_get.return_value = mock_router

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/")

    assert "FreeIA" in r.text
