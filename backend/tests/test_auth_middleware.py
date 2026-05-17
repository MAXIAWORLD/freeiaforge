"""
Tests TDD pour GatewayAuthMiddleware.

Cas couverts :
  - pas de clé configurée → tout passe
  - bonne clé Bearer → 200
  - header manquant → 401
  - mauvaise clé → 401
  - /health exempt même si clé configurée
  - clé vide string = auth désactivée
"""
from __future__ import annotations

import pytest
import httpx
from fastapi import FastAPI

from middleware.auth import GatewayAuthMiddleware

GATEWAY_KEY = "test-gateway-key-12345"


def _make_app(api_key: str | None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(GatewayAuthMiddleware, api_key=api_key)

    @app.get("/v1/chat/completions")
    async def chat():
        return {"ok": True}

    @app.get("/v1/models")
    async def models():
        return {"data": []}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.mark.asyncio
async def test_no_key_configured_allows_all():
    """FREEAI_API_KEY non configuré → tout passe sans auth."""
    app = _make_app(api_key=None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/v1/chat/completions")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_empty_key_disables_auth():
    """Clé vide string = auth désactivée."""
    app = _make_app(api_key="")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/v1/models")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_correct_bearer_token_passes():
    app = _make_app(api_key=GATEWAY_KEY)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {GATEWAY_KEY}"},
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_missing_header_returns_401():
    app = _make_app(api_key=GATEWAY_KEY)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/v1/chat/completions")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wrong_token_returns_401():
    app = _make_app(api_key=GATEWAY_KEY)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get(
            "/v1/models", headers={"Authorization": "Bearer wrong-key"}
        )
    assert r.status_code == 401
    data = r.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_health_exempt_with_key_configured():
    """/health ne requiert pas d'auth même si FREEAI_API_KEY est set."""
    app = _make_app(api_key=GATEWAY_KEY)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/health")
    assert r.status_code == 200
