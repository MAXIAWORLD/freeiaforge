import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from main import app
from core.models import ProviderStatus


def make_mock_router(statuses: list[ProviderStatus] | None = None):
    if statuses is None:
        statuses = [
            ProviderStatus(
                name="groq",
                available=True,
                requests_used=100,
                requests_limit=14400,
                tokens_used=50000,
                tokens_limit=500000,
                last_error=None,
                last_used_at=None,
                consecutive_errors=0,
            )
        ]
    mock_router = MagicMock()
    mock_router.get_provider_statuses = AsyncMock(return_value=statuses)
    return mock_router


@pytest.mark.asyncio
async def test_health_returns_ok():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_providers_returns_list():
    with patch("routes.health.get_router", return_value=make_mock_router()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/providers")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "groq"
    assert data[0]["available"] is True
    assert data[0]["requests_limit"] == 14400


@pytest.mark.asyncio
async def test_providers_returns_empty_when_no_providers():
    with patch("routes.health.get_router", return_value=make_mock_router(statuses=[])):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/providers")
    assert r.status_code == 200
    assert r.json() == []


# --- Phase 3 : nouveaux champs ProviderStatus ---


@pytest.mark.asyncio
async def test_providers_status_alias_returns_200():
    """GET /v1/providers/status doit retourner 200 (alias de /v1/providers)."""
    with patch("routes.health.get_router", return_value=make_mock_router()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/providers/status")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_providers_status_alias_same_content():
    """GET /v1/providers/status retourne le même contenu que /v1/providers."""
    mock_router = make_mock_router()
    with patch("routes.health.get_router", return_value=mock_router):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r_alias = await client.get("/v1/providers/status")
            r_orig = await client.get("/v1/providers")
    assert r_alias.json() == r_orig.json()


@pytest.mark.asyncio
async def test_providers_has_last_error_field():
    """La réponse /v1/providers doit contenir le champ last_error."""
    with patch("routes.health.get_router", return_value=make_mock_router()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/providers")
    assert "last_error" in r.json()[0]


@pytest.mark.asyncio
async def test_providers_has_last_used_at_field():
    """La réponse /v1/providers doit contenir le champ last_used_at."""
    with patch("routes.health.get_router", return_value=make_mock_router()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/providers")
    assert "last_used_at" in r.json()[0]


@pytest.mark.asyncio
async def test_providers_has_consecutive_errors_field():
    """La réponse /v1/providers doit contenir le champ consecutive_errors."""
    with patch("routes.health.get_router", return_value=make_mock_router()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/providers")
    assert "consecutive_errors" in r.json()[0]
    assert r.json()[0]["consecutive_errors"] == 0


@pytest.mark.asyncio
async def test_providers_last_error_populated_after_failure():
    """last_error doit être non-null quand le provider a échoué."""
    statuses = [
        ProviderStatus(
            name="cerebras",
            available=True,
            requests_used=0,
            requests_limit=1000,
            tokens_used=0,
            tokens_limit=100000,
            last_error="Provider 'cerebras' error (HTTP 429)",
            last_used_at=None,
            consecutive_errors=3,
        )
    ]
    with patch(
        "routes.health.get_router", return_value=make_mock_router(statuses=statuses)
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/providers")
    data = r.json()[0]
    assert data["last_error"] is not None
    assert data["consecutive_errors"] == 3
