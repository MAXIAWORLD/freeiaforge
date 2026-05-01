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
