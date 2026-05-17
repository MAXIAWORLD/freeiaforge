from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite


async def init_stats_db(db: "aiosqlite.Connection") -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS request_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL,
            task_type   TEXT NOT NULL,
            provider    TEXT NOT NULL,
            tokens_used INTEGER NOT NULL DEFAULT 0
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_ts ON request_log(ts)")
    await db.commit()


async def record_request(
    db: "aiosqlite.Connection",
    task_type: str,
    provider: str,
    tokens_used: int,
) -> None:
    ts = datetime.now(tz=timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO request_log (ts, task_type, provider, tokens_used) VALUES (?, ?, ?, ?)",
        (ts, task_type, provider, tokens_used),
    )
    await db.commit()


async def get_last_7_days(db: "aiosqlite.Connection") -> list[dict]:
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=7)).isoformat()
    async with db.execute(
        """
        SELECT substr(ts, 1, 10) AS day, task_type, provider,
               COUNT(*) AS requests, SUM(tokens_used) AS tokens
        FROM request_log
        WHERE ts >= ?
        GROUP BY day, task_type, provider
        ORDER BY day DESC, task_type
        """,
        (cutoff,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [
        {
            "day": row[0],
            "task_type": row[1],
            "provider": row[2],
            "requests": row[3],
            "tokens": row[4],
        }
        for row in rows
    ]
