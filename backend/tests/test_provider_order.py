"""Tests TDD pour PROVIDER_ORDER — FreeIA Gateway v0.3.0."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models import ChatRequest, ChatResponse, ChatChoice, ChatUsage, Message
from providers.base import ProviderResult
from services.router import ProviderRouter


def _make_provider(name: str, priority: int) -> MagicMock:
    p = MagicMock()
    p.name = name
    p.priority = priority
    return p


def _make_quota(available: bool = True) -> AsyncMock:
    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=available)
    quota.record_usage = AsyncMock()
    return quota


def _make_result(provider_name: str) -> ProviderResult:
    return ProviderResult(
        response=ChatResponse(
            id="t",
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


# ---------------------------------------------------------------------------
# Static ordering logic
# ---------------------------------------------------------------------------


class TestProviderOrderStatic:
    def test_no_order_sorts_by_priority(self):
        p1 = _make_provider("cerebras", 1)
        p2 = _make_provider("groq", 2)
        router = ProviderRouter(providers=[p2, p1], quota=_make_quota(), api_keys={})
        assert router._providers[0].name == "cerebras"
        assert router._providers[1].name == "groq"

    def test_custom_order_overrides_priority(self):
        p1 = _make_provider("cerebras", 1)
        p2 = _make_provider("groq", 2)
        router = ProviderRouter(
            providers=[p1, p2],
            quota=_make_quota(),
            api_keys={},
            provider_order=["groq", "cerebras"],
        )
        assert router._providers[0].name == "groq"
        assert router._providers[1].name == "cerebras"

    def test_partial_order_appends_rest_by_priority(self):
        p1 = _make_provider("cerebras", 1)
        p2 = _make_provider("groq", 2)
        p3 = _make_provider("gemini", 4)
        router = ProviderRouter(
            providers=[p1, p2, p3],
            quota=_make_quota(),
            api_keys={},
            provider_order=["gemini"],
        )
        assert router._providers[0].name == "gemini"
        assert router._providers[1].name == "cerebras"
        assert router._providers[2].name == "groq"

    def test_unknown_name_in_order_is_ignored(self):
        p1 = _make_provider("cerebras", 1)
        p2 = _make_provider("groq", 2)
        router = ProviderRouter(
            providers=[p1, p2],
            quota=_make_quota(),
            api_keys={},
            provider_order=["groq", "nonexistent"],
        )
        assert router._providers[0].name == "groq"
        assert router._providers[1].name == "cerebras"

    def test_empty_order_list_uses_priority(self):
        p1 = _make_provider("cerebras", 1)
        p2 = _make_provider("groq", 2)
        router = ProviderRouter(
            providers=[p2, p1],
            quota=_make_quota(),
            api_keys={},
            provider_order=[],
        )
        assert router._providers[0].name == "cerebras"

    def test_all_providers_in_order_uses_specified_sequence(self):
        p1 = _make_provider("cerebras", 1)
        p2 = _make_provider("groq", 2)
        p3 = _make_provider("gemini", 4)
        router = ProviderRouter(
            providers=[p1, p2, p3],
            quota=_make_quota(),
            api_keys={},
            provider_order=["gemini", "cerebras", "groq"],
        )
        assert [p.name for p in router._providers] == ["gemini", "cerebras", "groq"]


# ---------------------------------------------------------------------------
# Routing respects order
# ---------------------------------------------------------------------------


class TestProviderOrderRouting:
    @pytest.mark.asyncio
    async def test_routing_calls_first_ordered_provider(self):
        p1 = _make_provider("cerebras", 1)
        p1.complete = AsyncMock(return_value=_make_result("cerebras"))
        p2 = _make_provider("groq", 2)
        p2.complete = AsyncMock(return_value=_make_result("groq"))

        router = ProviderRouter(
            providers=[p1, p2],
            quota=_make_quota(),
            api_keys={"cerebras": "k1", "groq": "k2"},
            provider_order=["groq", "cerebras"],
        )
        result = await router.route(_make_request())

        assert result.provider_name == "groq"
        p1.complete.assert_not_called()
        p2.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_routing_falls_back_when_first_fails(self):
        from providers.base import ProviderError

        p1 = _make_provider("cerebras", 1)
        p1.complete = AsyncMock(return_value=_make_result("cerebras"))
        p2 = _make_provider("groq", 2)
        p2.complete = AsyncMock(side_effect=ProviderError("groq", 429))

        router = ProviderRouter(
            providers=[p1, p2],
            quota=_make_quota(),
            api_keys={"cerebras": "k1", "groq": "k2"},
            provider_order=["groq", "cerebras"],
        )
        result = await router.route(_make_request())

        assert result.provider_name == "cerebras"
