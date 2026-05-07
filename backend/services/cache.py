from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import aiosqlite

from core.models import ChatResponse, Message

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cache (
    key       TEXT PRIMARY KEY,
    payload   TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
"""

_INSERT = """
INSERT OR REPLACE INTO cache (key, payload, expires_at)
VALUES (?, ?, ?);
"""

_SELECT = """
SELECT payload FROM cache
WHERE key = ? AND expires_at > ?;
"""

_DELETE_EXPIRED = """
DELETE FROM cache WHERE expires_at <= ?;
"""


def _normalize_messages(messages: list[Message]) -> str:
    """Sérialise les messages en chaîne normalisée (lowercase + strip whitespace)."""
    parts: list[str] = []
    for msg in messages:
        role = msg.role.strip().lower()
        if isinstance(msg.content, str):
            content = " ".join(msg.content.lower().split())
        else:
            # Multimodal : sérialiser en JSON stable
            content = json.dumps(
                msg.content, sort_keys=True, ensure_ascii=False
            ).lower()
        parts.append(f"{role}:{content}")
    return "|".join(parts)


def _make_key(messages: list[Message]) -> str:
    normalized = _normalize_messages(messages)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class SemanticCache:
    """
    Cache exact basé sur SHA-256 du contenu normalisé des messages.
    Stockage : SQLite table `cache` dans data_dir/freeai.db.
    TTL expiration contrôlée par expires_at (Unix timestamp).

    Technologie choisie : SQLite (chromadb absent de requirements.txt).
    Un cache exact est utile pour les requêtes répétées identiques.
    """

    def __init__(self, data_dir: Path) -> None:
        self._db_path = data_dir / "freeai.db"
        self._initialized = False

    async def lookup(self, messages: list[Message]) -> ChatResponse | None:
        """Retourne la réponse cachée si disponible et non expirée, None sinon."""
        key = _make_key(messages)
        now = int(time.time())
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(_CREATE_TABLE)
                await db.commit()
                async with db.execute(_SELECT, (key, now)) as cursor:
                    row = await cursor.fetchone()
                if row is None:
                    return None
                return ChatResponse.model_validate_json(row[0])
        except Exception as exc:
            logger.warning("Cache lookup failed: %s", exc)
            return None

    async def store(
        self,
        messages: list[Message],
        response: ChatResponse,
        ttl_seconds: int,
    ) -> None:
        """Stocke la réponse avec TTL (en secondes)."""
        key = _make_key(messages)
        payload = response.model_dump_json()
        expires_at = int(time.time()) + ttl_seconds
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(_CREATE_TABLE)
                await db.execute(_INSERT, (key, payload, expires_at))
                # Nettoyage opportuniste des entrées expirées
                await db.execute(_DELETE_EXPIRED, (int(time.time()),))
                await db.commit()
        except Exception as exc:
            logger.warning("Cache store failed: %s", exc)
