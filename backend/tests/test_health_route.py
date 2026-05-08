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


def make_mock_router_with_providers(api_keys: dict[str, str] | None = None):
    if api_keys is None:
        api_keys = {"cerebras": "csk-test"}
    mock_router = MagicMock()
    mock_router._api_keys = api_keys
    cerebras_provider = MagicMock()
    cerebras_provider.name = "cerebras"
    cerebras_provider.default_model = "llama-3.3-70b"
    groq_provider = MagicMock()
    groq_provider.name = "groq"
    groq_provider.default_model = "llama-3.3-70b-versatile"
    ollama_provider = MagicMock()
    ollama_provider.name = "ollama"
    ollama_provider.default_model = "llama3.2"
    mock_router._providers = [cerebras_provider, groq_provider, ollama_provider]
    return mock_router


@pytest.mark.asyncio
async def test_models_returns_openai_compatible_list():
    """GET /v1/models doit retourner le format OpenAI {object:'list', data:[...]}."""
    with patch(
        "routes.health.get_router", return_value=make_mock_router_with_providers()
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/models")
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "list"
    assert isinstance(data["data"], list)
    ids = {m["id"] for m in data["data"]}
    assert "freeai-gateway" in ids
    for entry in data["data"]:
        assert entry["object"] == "model"
        assert "created" in entry
        assert "owned_by" in entry


@pytest.mark.asyncio
async def test_models_includes_provider_models_when_keys_set():
    """GET /v1/models inclut les default_model des providers ayant une clé API."""
    with patch(
        "routes.health.get_router",
        return_value=make_mock_router_with_providers({"cerebras": "csk-test"}),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/models")
    ids = {m["id"] for m in r.json()["data"]}
    assert "llama-3.3-70b" in ids  # cerebras
    assert "llama3.2" in ids  # ollama (no key needed)
    assert "llama-3.3-70b-versatile" not in ids  # groq has no key


@pytest.mark.asyncio
async def test_models_skips_providers_without_keys():
    """Sans clé API, les providers cloud n'apparaissent pas (sauf Ollama)."""
    with patch(
        "routes.health.get_router",
        return_value=make_mock_router_with_providers({}),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/v1/models")
    ids = {m["id"] for m in r.json()["data"]}
    assert "freeai-gateway" in ids
    assert "llama3.2" in ids  # ollama always present
    assert "llama-3.3-70b" not in ids  # cerebras has no key


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
