"""TDD — JSON logging configuration (Phase A jour 5, freeiaforge v0.6.0)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# JsonFormatter
# ---------------------------------------------------------------------------


def test_json_formatter_emits_valid_json_with_core_fields():
    from core.logging_config import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="services.router",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    output = formatter.format(record)
    payload = json.loads(output)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "services.router"
    assert payload["message"] == "hello world"
    assert "ts" in payload


def test_json_formatter_includes_exception_traceback():
    from core.logging_config import JsonFormatter

    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="x",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="caught",
            args=None,
            exc_info=sys.exc_info(),
        )
    payload = json.loads(formatter.format(record))
    assert "exc" in payload
    assert "ValueError" in payload["exc"]
    assert "boom" in payload["exc"]


def test_json_formatter_propagates_extra_fields():
    """Extras passed via logger.info("...", extra={"provider": "groq"}) must
    appear at the top level of the JSON payload."""
    from core.logging_config import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="ok",
        args=None,
        exc_info=None,
    )
    record.provider = "groq"
    record.tokens_used = 42
    payload = json.loads(formatter.format(record))
    assert payload["provider"] == "groq"
    assert payload["tokens_used"] == 42


# ---------------------------------------------------------------------------
# configure_logging — console + rotating JSON file
# ---------------------------------------------------------------------------


def test_configure_logging_creates_log_file(tmp_path: Path):
    from core.logging_config import configure_logging

    log_dir = tmp_path / "logs"
    configure_logging(log_dir=str(log_dir))

    log = logging.getLogger("freeiaforge.test")
    log.setLevel(logging.INFO)
    log.info("hello world")

    # Force flush of all handlers attached to root
    for h in logging.getLogger().handlers:
        h.flush()

    log_file = log_dir / "freeiaforge.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "hello world" in content
    # Each line should be parseable JSON
    last_line = [line for line in content.splitlines() if line.strip()][-1]
    payload = json.loads(last_line)
    assert payload["message"] == "hello world"


def test_configure_logging_uses_rotating_handler(tmp_path: Path):
    """The file handler must be a RotatingFileHandler so logs don't grow forever."""
    import logging.handlers

    from core.logging_config import configure_logging

    configure_logging(log_dir=str(tmp_path / "logs"))
    rotating = [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert rotating, "expected a RotatingFileHandler attached to root logger"
    handler = rotating[0]
    assert handler.maxBytes > 0
    assert handler.backupCount >= 1


@pytest.fixture(autouse=True)
def _isolate_root_logger():
    """Each test starts from a clean root logger to avoid handler bleed."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    yield
    for h in list(root.handlers):
        if h not in saved_handlers:
            root.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
    root.setLevel(saved_level)
