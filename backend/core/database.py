from __future__ import annotations
import aiosqlite


async def init_db(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS quota (
            provider TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            requests_used INTEGER NOT NULL DEFAULT 0,
            tokens_used INTEGER NOT NULL DEFAULT 0
        )
    """)
    await db.commit()


async def close_db(db: aiosqlite.Connection) -> None:
    await db.close()
