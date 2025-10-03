"""Structured logging utilities for Sprint Bot."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

__all__ = ["get_logger"]


class JsonLogFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - inherited doc
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
            "user_id": getattr(record, "user_id", None),
            "cmd": getattr(record, "cmd", None),
            "latency_ms": getattr(record, "latency_ms", None),
        }
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """Return logger configured with JSON ``StreamHandler`` output."""

    logger = logging.getLogger(name)
    if not any(getattr(handler, "_is_sprint_json", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        handler._is_sprint_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
