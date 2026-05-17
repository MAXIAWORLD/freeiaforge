"""
Tests TDD — Circuit Breaker 3 états (Phase 1).

États : CLOSED → OPEN → HALF_OPEN → CLOSED

Cas couverts :
  - N erreurs >= threshold → OPEN
  - Provider OPEN skipé dans route()
  - Après CB_HALF_OPEN_AFTER secondes → HALF_OPEN (probe autorisé)
  - Probe HALF_OPEN réussi → CLOSED
  - Probe HALF_OPEN échoué → retour OPEN (timer reset)
  - Erreur 400 ne compte pas
  - Erreur 401 ne compte pas
  - Succès reset errors + CLOSED
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request() -> ChatRequest:
    return ChatRequest(messages=[Message(role="user", content="hi")])


def _make_result(name: str) -> ProviderResult:
    return ProviderResult(
        response=ChatResponse(
            id="x",
            model="m",
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


def _router(providers, cb_failure_threshold=3, cb_half_open_after=300) -> ProviderRouter:
    api_keys = {p.name: "key" for p in providers}
    return ProviderRouter(
        providers=providers,
        quota=_mock_quota_ok(),
        api_keys=api_keys,
        cb_failure_threshold=cb_failure_threshold,
        cb_half_open_after=cb_half_open_after,
    )


# ---------------------------------------------------------------------------
# CLOSED → OPEN
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_errors():
    """N=3 erreurs 503 consécutives → circuit OPEN."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 1
    p1.complete = AsyncMock(side_effect=ProviderError("groq", status_code=503))

    p2 = AsyncMock()
    p2.name = "ollama"
    p2.priority = 9
    p2.complete = AsyncMock(return_value=_make_result("ollama"))

    router = _router([p1, p2], cb_failure_threshold=3)

    for _ in range(3):
        await router.route(_make_request())

    assert router._error_state["groq"]["circuit_status"] == "OPEN"


@pytest.mark.asyncio
async def test_circuit_not_opened_below_threshold():
    """2 erreurs < threshold=3 → reste CLOSED."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 1
    p1.complete = AsyncMock(side_effect=ProviderError("groq", status_code=500))

    p2 = AsyncMock()
    p2.name = "ollama"
    p2.priority = 9
    p2.complete = AsyncMock(return_value=_make_result("ollama"))

    router = _router([p1, p2], cb_failure_threshold=3)
    await router.route(_make_request())
    await router.route(_make_request())

    status = router._error_state.get("groq", {}).get("circuit_status", "CLOSED")
    assert status == "CLOSED"


# ---------------------------------------------------------------------------
# OPEN → provider skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_circuit_provider_is_skipped():
    """Un provider OPEN ne doit pas être appelé."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 1
    p1.complete = AsyncMock(return_value=_make_result("groq"))

    p2 = AsyncMock()
    p2.name = "ollama"
    p2.priority = 9
    p2.complete = AsyncMock(return_value=_make_result("ollama"))

    router = _router([p1, p2])
    # Forcer circuit OPEN sans timeout
    router._error_state["groq"] = {
        "consecutive_errors": 5,
        "last_error": "forced",
        "last_used_at": None,
        "circuit_status": "OPEN",
        "open_since": datetime.now(tz=timezone.utc).isoformat(),
    }

    result = await router.route(_make_request())

    p1.complete.assert_not_called()
    assert result.provider_name == "ollama"


# ---------------------------------------------------------------------------
# OPEN → HALF_OPEN (après timeout)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_transitions_to_half_open_after_timeout():
    """Après CB_HALF_OPEN_AFTER secondes, le provider OPEN doit être tenté."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 1
    p1.complete = AsyncMock(return_value=_make_result("groq"))

    router = _router([p1], cb_half_open_after=300)
    # open_since = il y a 400s (> 300s threshold)
    past = (datetime.now(tz=timezone.utc) - timedelta(seconds=400)).isoformat()
    router._error_state["groq"] = {
        "consecutive_errors": 3,
        "last_error": "HTTP 503",
        "last_used_at": None,
        "circuit_status": "OPEN",
        "open_since": past,
    }

    result = await router.route(_make_request())

    p1.complete.assert_called_once()
    assert result.provider_name == "groq"


@pytest.mark.asyncio
async def test_open_not_retried_before_timeout():
    """Avant le timeout, le provider OPEN reste skipé."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 1
    p1.complete = AsyncMock(return_value=_make_result("groq"))

    p2 = AsyncMock()
    p2.name = "ollama"
    p2.priority = 9
    p2.complete = AsyncMock(return_value=_make_result("ollama"))

    router = _router([p1, p2], cb_half_open_after=300)
    # open_since = il y a seulement 10s (< 300s)
    recent = (datetime.now(tz=timezone.utc) - timedelta(seconds=10)).isoformat()
    router._error_state["groq"] = {
        "consecutive_errors": 3,
        "last_error": "HTTP 503",
        "last_used_at": None,
        "circuit_status": "OPEN",
        "open_since": recent,
    }

    result = await router.route(_make_request())

    p1.complete.assert_not_called()
    assert result.provider_name == "ollama"


# ---------------------------------------------------------------------------
# HALF_OPEN probe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_half_open_success_closes_circuit():
    """Probe HALF_OPEN réussi → CLOSED."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 1
    p1.complete = AsyncMock(return_value=_make_result("groq"))

    router = _router([p1])
    router._error_state["groq"] = {
        "consecutive_errors": 3,
        "last_error": "old error",
        "last_used_at": None,
        "circuit_status": "HALF_OPEN",
        "open_since": None,
    }

    await router.route(_make_request())

    assert router._error_state["groq"]["circuit_status"] == "CLOSED"
    assert router._error_state["groq"]["consecutive_errors"] == 0


@pytest.mark.asyncio
async def test_half_open_failure_reopens_circuit():
    """Probe HALF_OPEN échoué → retour OPEN avec timer reset."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 1
    p1.complete = AsyncMock(side_effect=ProviderError("groq", status_code=503))

    p2 = AsyncMock()
    p2.name = "ollama"
    p2.priority = 9
    p2.complete = AsyncMock(return_value=_make_result("ollama"))

    router = _router([p1, p2])
    router._error_state["groq"] = {
        "consecutive_errors": 3,
        "last_error": "old error",
        "last_used_at": None,
        "circuit_status": "HALF_OPEN",
        "open_since": None,
    }

    await router.route(_make_request())

    assert router._error_state["groq"]["circuit_status"] == "OPEN"
    assert router._error_state["groq"]["open_since"] is not None


# ---------------------------------------------------------------------------
# Erreurs ignorées par le CB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_400_does_not_count_toward_circuit():
    """Erreur 400 (mauvaise requête user) ne doit pas incrémenter les erreurs CB."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 1
    p1.complete = AsyncMock(side_effect=ProviderError("groq", status_code=400))

    p2 = AsyncMock()
    p2.name = "ollama"
    p2.priority = 9
    p2.complete = AsyncMock(return_value=_make_result("ollama"))

    router = _router([p1, p2], cb_failure_threshold=3)
    for _ in range(5):
        await router.route(_make_request())

    status = router._error_state.get("groq", {}).get("circuit_status", "CLOSED")
    assert status == "CLOSED"


@pytest.mark.asyncio
async def test_401_does_not_count_toward_circuit():
    """Erreur 401 (clé invalide) ne doit pas incrémenter les erreurs CB."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 1
    p1.complete = AsyncMock(side_effect=ProviderError("groq", status_code=401))

    p2 = AsyncMock()
    p2.name = "ollama"
    p2.priority = 9
    p2.complete = AsyncMock(return_value=_make_result("ollama"))

    router = _router([p1, p2], cb_failure_threshold=3)
    for _ in range(5):
        await router.route(_make_request())

    status = router._error_state.get("groq", {}).get("circuit_status", "CLOSED")
    assert status == "CLOSED"


# ---------------------------------------------------------------------------
# Reset sur succès
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_success_resets_errors_and_closes_circuit():
    """Succès après erreurs → consecutive_errors=0, circuit CLOSED."""
    p1 = AsyncMock()
    p1.name = "groq"
    p1.priority = 1
    p1.complete = AsyncMock(return_value=_make_result("groq"))

    router = _router([p1])
    router._error_state["groq"] = {
        "consecutive_errors": 2,
        "last_error": "HTTP 500",
        "last_used_at": None,
        "circuit_status": "CLOSED",
        "open_since": None,
    }

    await router.route(_make_request())

    assert router._error_state["groq"]["consecutive_errors"] == 0
    assert router._error_state["groq"]["circuit_status"] == "CLOSED"
