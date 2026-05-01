from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from mempalace.searcher import search_memories
except ImportError:
    logger.warning("mempalace not installed — memory features disabled")

    def search_memories(*args, **kwargs) -> dict:  # type: ignore[misc]
        return {"error": "mempalace not installed", "hint": "pip install mempalace"}


class MemPalaceService:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._palace_path = data_dir / "mempalace"
        self._transcripts_dir = data_dir / "transcripts"
        self._transcripts_dir.mkdir(parents=True, exist_ok=True)

    async def query(self, text: str, n: int = 5) -> list[str]:
        try:
            raw = await asyncio.to_thread(
                search_memories,
                query=text,
                palace_path=str(self._palace_path),
                n_results=n,
            )
            if "error" in raw:
                logger.warning("MemPalace query error: %s", raw.get("error"))
                return []
            return [item["text"] for item in raw.get("results", [])]
        except Exception as exc:
            logger.warning("MemPalace query failed: %s", exc)
            return []

    async def store(self, user_msg: str, assistant_msg: str) -> None:
        try:
            ts = int(time.time() * 1000)
            transcript_file = self._transcripts_dir / f"exchange_{ts}.txt"
            transcript_file.write_text(
                f"User: {user_msg}\nAssistant: {assistant_msg}\n",
                encoding="utf-8",
            )
            proc = await asyncio.create_subprocess_exec(
                "mempalace",
                "sweep",
                str(self._transcripts_dir),
                "--wing",
                "freeai",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        except Exception as exc:
            logger.warning("MemPalace store failed: %s", exc)
