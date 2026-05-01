from __future__ import annotations
from datetime import date
import aiosqlite
from core.models import ProviderStatus


class QuotaService:
    def __init__(
        self, db: aiosqlite.Connection, limits: dict[str, dict[str, int]]
    ) -> None:
        self._db = db
        self._limits = limits

    def _today(self) -> str:
        return date.today().isoformat()

    async def _get_row(self, provider: str) -> tuple[int, int] | None:
        today = self._today()
        async with self._db.execute(
            "SELECT requests_used, tokens_used FROM quota WHERE provider=? AND date=?",
            (provider, today),
        ) as cursor:
            return await cursor.fetchone()

    async def is_available(self, provider: str) -> bool:
        if provider not in self._limits:
            return False
        row = await self._get_row(provider)
        if row is None:
            return True
        req_used, tok_used = row
        limits = self._limits[provider]
        return req_used < limits["requests"] and tok_used < limits["tokens"]

    async def record_usage(self, provider: str, requests: int, tokens: int) -> None:
        today = self._today()
        await self._db.execute(
            """
            INSERT INTO quota (provider, date, requests_used, tokens_used)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET
                requests_used = CASE WHEN date=excluded.date THEN requests_used+excluded.requests_used ELSE excluded.requests_used END,
                tokens_used   = CASE WHEN date=excluded.date THEN tokens_used+excluded.tokens_used ELSE excluded.tokens_used END,
                date          = excluded.date
        """,
            (provider, today, requests, tokens),
        )
        await self._db.commit()

    async def reset(self, provider: str) -> None:
        today = self._today()
        await self._db.execute(
            "UPDATE quota SET requests_used=0, tokens_used=0, date=? WHERE provider=?",
            (today, provider),
        )
        await self._db.commit()

    async def get_status(self, provider: str) -> ProviderStatus:
        limits = self._limits.get(provider, {"requests": 0, "tokens": 0})
        row = await self._get_row(provider)
        req_used, tok_used = row if row else (0, 0)
        return ProviderStatus(
            name=provider,
            available=await self.is_available(provider),
            requests_used=req_used,
            requests_limit=limits["requests"],
            tokens_used=tok_used,
            tokens_limit=limits["tokens"],
        )
