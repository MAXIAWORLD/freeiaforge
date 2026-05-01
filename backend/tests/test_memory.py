from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper — build a MemPalaceService with a real temp dir
# ---------------------------------------------------------------------------

def _make_service(tmp_path: Path):
    from services.memory import MemPalaceService
    return MemPalaceService(data_dir=tmp_path)


# ---------------------------------------------------------------------------
# query — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_returns_text_strings_on_success(tmp_path):
    service = _make_service(tmp_path)
    fake_results = {
        "query": "why GraphQL",
        "results": [
            {"text": "foo", "wing": "w1", "room": "r1", "similarity": 0.9},
            {"text": "bar", "wing": "w1", "room": "r2", "similarity": 0.8},
        ],
    }
    with patch("services.memory.search_memories", return_value=fake_results):
        result = await service.query("why GraphQL", n=5)

    assert result == ["foo", "bar"]


# ---------------------------------------------------------------------------
# query — error dict returned by search_memories
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_returns_empty_list_when_error_key(tmp_path):
    service = _make_service(tmp_path)
    fake_error = {"error": "palace not found", "hint": "run mempalace init"}
    with patch("services.memory.search_memories", return_value=fake_error):
        result = await service.query("anything")

    assert result == []


# ---------------------------------------------------------------------------
# query — search_memories raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_returns_empty_list_on_exception(tmp_path):
    service = _make_service(tmp_path)
    with patch("services.memory.search_memories", side_effect=RuntimeError("boom")):
        result = await service.query("anything")

    assert result == []


# ---------------------------------------------------------------------------
# query — empty results list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_returns_empty_list_when_no_results(tmp_path):
    service = _make_service(tmp_path)
    with patch("services.memory.search_memories", return_value={"query": "x", "results": []}):
        result = await service.query("x")

    assert result == []


# ---------------------------------------------------------------------------
# store — transcript file created
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_creates_transcript_file(tmp_path):
    from unittest.mock import AsyncMock as _AsyncMock
    service = _make_service(tmp_path)
    transcripts_dir = tmp_path / "transcripts"

    # Patch subprocess so we don't actually call mempalace sweep
    proc = MagicMock()
    proc.communicate = _AsyncMock(return_value=(b"", b""))
    with patch("services.memory.asyncio.create_subprocess_exec", new_callable=_AsyncMock, return_value=proc):
        await service.store("hello", "world")

    txt_files = list(transcripts_dir.glob("*.txt"))
    assert len(txt_files) == 1
    content = txt_files[0].read_text(encoding="utf-8")
    assert "hello" in content
    assert "world" in content


# ---------------------------------------------------------------------------
# store — transcripts dir created by constructor
# ---------------------------------------------------------------------------

def test_constructor_creates_transcripts_dir(tmp_path):
    data_dir = tmp_path / "mydata"
    data_dir.mkdir()
    _make_service(data_dir)
    assert (data_dir / "transcripts").is_dir()


# ---------------------------------------------------------------------------
# store — subprocess failure is silent (graceful degradation)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_silent_on_subprocess_failure(tmp_path):
    service = _make_service(tmp_path)
    with patch("services.memory.asyncio.create_subprocess_exec", side_effect=OSError("no binary")):
        # Must not raise
        await service.store("hello", "world")


# ---------------------------------------------------------------------------
# store — any generic exception is silent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_silent_on_generic_exception(tmp_path):
    service = _make_service(tmp_path)
    with patch("services.memory.asyncio.create_subprocess_exec", side_effect=Exception("unexpected")):
        await service.store("msg", "reply")


# ---------------------------------------------------------------------------
# store — file write failure is silent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_silent_on_write_failure(tmp_path):
    service = _make_service(tmp_path)
    with patch("builtins.open", side_effect=PermissionError("denied")):
        await service.store("msg", "reply")
