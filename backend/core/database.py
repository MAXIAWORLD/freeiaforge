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
    await db.execute("""
        CREATE TABLE IF NOT EXISTS credential_pool_state (
            provider TEXT NOT NULL,
            key_hash TEXT NOT NULL,
            cooldown_until TEXT,
            fail_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (provider, key_hash)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS circuit_state (
            provider TEXT PRIMARY KEY,
            consecutive_errors INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            last_used_at TEXT
        )
    """)
    # Migration: add circuit_status + open_since columns (idempotent)
    for col, typedef in [
        ("circuit_status", "TEXT NOT NULL DEFAULT 'CLOSED'"),
        ("open_since", "TEXT"),
    ]:
        try:
            await db.execute(
                f"ALTER TABLE circuit_state ADD COLUMN {col} {typedef}"
            )
        except Exception:
            pass  # column already exists
    await db.commit()


async def close_db(db: aiosqlite.Connection) -> None:
    await db.close()
