import pytest
from services.quota import QuotaService


@pytest.mark.asyncio
async def test_fresh_provider_is_available(quota: QuotaService) -> None:
    assert await quota.is_available("cerebras") is True


@pytest.mark.asyncio
async def test_record_usage_increments_counters(quota: QuotaService) -> None:
    await quota.record_usage("groq", requests=1, tokens=500)
    status = await quota.get_status("groq")
    assert status.requests_used == 1
    assert status.tokens_used == 500


@pytest.mark.asyncio
async def test_provider_unavailable_when_requests_exhausted(
    quota: QuotaService,
) -> None:
    await quota.record_usage("groq", requests=2, tokens=0)
    assert await quota.is_available("groq") is False


@pytest.mark.asyncio
async def test_provider_unavailable_when_tokens_exhausted(quota: QuotaService) -> None:
    await quota.record_usage("mistral", requests=0, tokens=200_000)
    assert await quota.is_available("mistral") is False


@pytest.mark.asyncio
async def test_reset_restores_availability(quota: QuotaService) -> None:
    await quota.record_usage("groq", requests=2, tokens=0)
    await quota.reset("groq")
    assert await quota.is_available("groq") is True


@pytest.mark.asyncio
async def test_unknown_provider_is_unavailable(quota: QuotaService) -> None:
    assert await quota.is_available("nonexistent") is False


@pytest.mark.asyncio
async def test_record_usage_resets_on_date_rollover(quota: QuotaService) -> None:
    from datetime import date, timedelta

    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # Manually insert a row dated yesterday
    async with quota._db.execute(
        "INSERT INTO quota (provider, date, requests_used, tokens_used) VALUES (?, ?, ?, ?)",
        ("cerebras", yesterday, 9999, 999_000),
    ):
        pass
    await quota._db.commit()

    # Record usage today — should reset, not accumulate
    await quota.record_usage("cerebras", requests=1, tokens=100)

    status = await quota.get_status("cerebras")
    assert status.requests_used == 1, f"Expected 1, got {status.requests_used}"
    assert status.tokens_used == 100, f"Expected 100, got {status.tokens_used}"
