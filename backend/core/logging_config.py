"""Structured logging configuration for FreeIA Gateway.

Provides:
- ``JsonFormatter`` — emits each ``LogRecord`` as a single JSON object on a
  line, with timestamp/level/logger/message plus any ``extra={}`` fields the
  caller attached. Easy to grep, easy to ship to log aggregators.
- ``configure_logging(log_dir, level)`` — wires a human-readable stream
  handler on stdout (kept for ``docker compose logs`` UX) and a rotating
  JSON file handler under ``{log_dir}/freeiaforge.log`` (10×10 MB).

Design notes:
- We deliberately don't take a runtime dependency on ``python-json-logger``;
  the formatter is short enough to maintain in-tree.
- ``configure_logging`` is idempotent — repeated calls won't pile up
  handlers because we tag the ones we add.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from typing import Any


_DEFAULT_LOG_FILE = "freeiaforge.log"
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
_DEFAULT_BACKUP_COUNT = 10  # ⇒ 10 × 10 MB = ~100 MB cap
_HANDLER_TAG = "_freeiaforge_managed"

_STANDARD_RECORD_KEYS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_KEYS or key.startswith("_"):
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(
    log_dir: str = "data/logs",
    level: int = logging.INFO,
) -> None:
    os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    # Drop any handler we previously attached so this function stays idempotent.
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_TAG, False):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # pragma: no cover — defensive
                pass

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    setattr(stream_handler, _HANDLER_TAG, True)
    root.addHandler(stream_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, _DEFAULT_LOG_FILE),
        maxBytes=_DEFAULT_MAX_BYTES,
        backupCount=_DEFAULT_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonFormatter())
    setattr(file_handler, _HANDLER_TAG, True)
    root.addHandler(file_handler)
