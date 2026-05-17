"""
Tests TDD — tri dynamique des providers par quota restant (Phase 1).

Le router doit trier les providers par (requests_limit - requests_used) / requests_limit
descendant à chaque appel, pas seulement au démarrage.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.models import ChatRequest, ChatResponse, ChatChoice, ChatUsage, Message, ProviderStatus
from providers.base import ProviderResult
from services.router import ProviderRouter


def _make_request() -> ChatRequest:
    return ChatRequest(messages=[Message(role="user", content="hi")])


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


def _mock_quota(statuses: dict[str, tuple[int, int]]) -> AsyncMock:
    """statuses = {provider_name: (requests_used, requests_limit)}"""
    quota = AsyncMock()

    async def _is_available(name: str) -> bool:
        used, limit = statuses.get(name, (0, 1000))
        return used < limit

    async def _status(name: str) -> ProviderStatus:
        used, limit = statuses.get(name, (0, 1000))
        return ProviderStatus(
            name=name, available=used < limit,
            requests_used=used, requests_limit=limit,
            tokens_used=0, tokens_limit=1_000_000,
        )

    quota.is_available = AsyncMock(side_effect=_is_available)
    quota.record_usage = AsyncMock()
    quota.get_status = AsyncMock(side_effect=_status)
    return quota


@pytest.mark.asyncio
async def test_provider_with_more_quota_tried_first():
    """Provider avec plus de quota restant doit être tenté en premier."""
    p_almost_full = AsyncMock()
    p_almost_full.name = "groq"
    p_almost_full.priority = 2
    p_almost_full.complete = AsyncMock(return_value=_make_result("groq"))

    p_nearly_empty = AsyncMock()
    p_nearly_empty.name = "cerebras"
    p_nearly_empty.priority = 1  # priority plus haute (=préféré statiquement)
    p_nearly_empty.complete = AsyncMock(return_value=_make_result("cerebras"))

    # Cerebras: 990/1000 utilisés (1% restant)
    # Groq: 100/1000 utilisés (90% restant)
    quota = _mock_quota({
        "cerebras": (990, 1000),
        "groq": (100, 1000),
    })

    router = ProviderRouter(
        providers=[p_almost_full, p_nearly_empty],
        quota=quota,
        api_keys={"groq": "k1", "cerebras": "k2"},
    )

    result = await router.route(_make_request())

    # Groq a plus de quota restant → doit être servi en premier
    assert result.provider_name == "groq"
    p_nearly_empty.complete.assert_not_called()


@pytest.mark.asyncio
async def test_quota_exhausted_provider_is_skipped():
    """Provider avec quota 0 doit être skipé même si priorité haute."""
    p_exhausted = AsyncMock()
    p_exhausted.name = "cerebras"
    p_exhausted.priority = 1
    p_exhausted.complete = AsyncMock(return_value=_make_result("cerebras"))

    p_available = AsyncMock()
    p_available.name = "groq"
    p_available.priority = 2
    p_available.complete = AsyncMock(return_value=_make_result("groq"))

    # Cerebras complètement épuisé
    quota = _mock_quota({
        "cerebras": (1000, 1000),
        "groq": (0, 1000),
    })

    router = ProviderRouter(
        providers=[p_exhausted, p_available],
        quota=quota,
        api_keys={"cerebras": "k1", "groq": "k2"},
    )

    result = await router.route(_make_request())

    assert result.provider_name == "groq"
    p_exhausted.complete.assert_not_called()


@pytest.mark.asyncio
async def test_equal_quota_preserves_priority_order():
    """À quota égal, l'ordre de priorité (priority field) est conservé."""
    p1 = AsyncMock()
    p1.name = "cerebras"
    p1.priority = 1
    p1.complete = AsyncMock(return_value=_make_result("cerebras"))

    p2 = AsyncMock()
    p2.name = "groq"
    p2.priority = 2
    p2.complete = AsyncMock(return_value=_make_result("groq"))

    # Quota identique
    quota = _mock_quota({
        "cerebras": (0, 1000),
        "groq": (0, 1000),
    })

    router = ProviderRouter(
        providers=[p1, p2],
        quota=quota,
        api_keys={"cerebras": "k1", "groq": "k2"},
    )

    result = await router.route(_make_request())

    # Priorité 1 < 2 → cerebras en premier
    assert result.provider_name == "cerebras"
