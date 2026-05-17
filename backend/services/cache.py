from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

from core.models import ChatResponse, Message

if TYPE_CHECKING:
    import numpy as np

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


class ExactCache:
    """
    Cache exact basé sur SHA-256 du contenu normalisé des messages.
    Stockage : SQLite table `cache` dans data_dir/cache.db.
    TTL expiration contrôlée par expires_at (Unix timestamp).
    """

    def __init__(self, data_dir: Path) -> None:
        self._db_path = data_dir / "cache.db"
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


# ---------------------------------------------------------------------------
# SemanticCache — fastembed + cosine similarity
# ---------------------------------------------------------------------------

_SC_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS semantic_cache (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_hash   TEXT NOT NULL UNIQUE,
    embedding  BLOB NOT NULL,
    payload    TEXT NOT NULL,
    expires_at INTEGER NOT NULL
)
"""
_SC_CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_sc_expires ON semantic_cache(expires_at)"


def _messages_to_text(messages: list[Message]) -> str:
    parts: list[str] = []
    for msg in messages:
        role = msg.role.strip().lower()
        if isinstance(msg.content, str):
            content = " ".join(msg.content.lower().split())
        else:
            content = json.dumps(msg.content, sort_keys=True, ensure_ascii=False).lower()
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


class SemanticCache:
    """
    Cache sémantique : embed les messages avec fastembed (all-MiniLM-L6-v2),
    retourne un hit si cosine similarity >= similarity_threshold.
    Stockage : SQLite table `semantic_cache` dans data_dir/cache.db.
    TTL expiration contrôlée par expires_at (Unix timestamp).
    """

    def __init__(
        self,
        data_dir: Path,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        similarity_threshold: float = 0.90,
    ) -> None:
        self._db_path = data_dir / "cache.db"
        self._model_name = model_name
        self._threshold = similarity_threshold
        self._model = None

    async def _get_model(self):
        if self._model is None:
            from fastembed import TextEmbedding
            loop = asyncio.get_event_loop()
            name = self._model_name
            self._model = await loop.run_in_executor(None, TextEmbedding, name)
        return self._model

    async def _embed(self, text: str) -> "np.ndarray":
        import numpy as np
        model = await self._get_model()
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: list(model.embed([text])))
        return results[0].astype(np.float32)

    @staticmethod
    def _cosine_sim(a: "np.ndarray", b: "np.ndarray") -> float:
        import numpy as np
        denom = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
        if denom < 1e-9:
            return 0.0
        return float(np.dot(a, b) / denom)

    async def _init_db(self, db: aiosqlite.Connection) -> None:
        await db.execute(_SC_CREATE_TABLE)
        await db.execute(_SC_CREATE_INDEX)
        await db.commit()

    async def lookup(self, messages: list[Message]) -> ChatResponse | None:
        import numpy as np
        text = _messages_to_text(messages)
        try:
            query_vec = await self._embed(text)
        except Exception as exc:
            logger.warning("SemanticCache embed failed on lookup: %s", exc)
            return None

        now = int(time.time())
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await self._init_db(db)
                async with db.execute(
                    "SELECT embedding, payload FROM semantic_cache WHERE expires_at > ?",
                    (now,),
                ) as cursor:
                    rows = await cursor.fetchall()
        except Exception as exc:
            logger.warning("SemanticCache db lookup error: %s", exc)
            return None

        if not rows:
            return None

        best_sim = -1.0
        best_payload: str | None = None
        for emb_bytes, payload in rows:
            vec = np.frombuffer(emb_bytes, dtype=np.float32)
            sim = self._cosine_sim(query_vec, vec)
            if sim > best_sim:
                best_sim = sim
                best_payload = payload

        if best_sim >= self._threshold and best_payload is not None:
            logger.debug("SemanticCache hit (sim=%.3f)", best_sim)
            try:
                return ChatResponse.model_validate_json(best_payload)
            except Exception:
                return None

        logger.debug("SemanticCache miss (best_sim=%.3f < %.2f)", best_sim, self._threshold)
        return None

    async def store(
        self,
        messages: list[Message],
        response: ChatResponse,
        ttl_seconds: int,
    ) -> None:
        import numpy as np
        text = _messages_to_text(messages)
        try:
            vec = await self._embed(text)
        except Exception as exc:
            logger.warning("SemanticCache embed failed on store: %s", exc)
            return

        msg_hash = hashlib.sha256(text.encode()).hexdigest()
        emb_bytes = vec.astype(np.float32).tobytes()
        payload = response.model_dump_json()
        expires_at = int(time.time()) + ttl_seconds

        try:
            async with aiosqlite.connect(self._db_path) as db:
                await self._init_db(db)
                await db.execute(
                    "INSERT OR REPLACE INTO semantic_cache (msg_hash, embedding, payload, expires_at)"
                    " VALUES (?, ?, ?, ?)",
                    (msg_hash, emb_bytes, payload, expires_at),
                )
                await db.execute(
                    "DELETE FROM semantic_cache WHERE expires_at <= ?", (int(time.time()),)
                )
                await db.commit()
        except Exception as exc:
            logger.warning("SemanticCache store failed: %s", exc)
