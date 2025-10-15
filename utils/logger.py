"""Structured logging utilities for Sprint Bot."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from utils.personal_data import scrub_sensitive_mapping

__all__ = ["get_logger"]

LOG_DIR = Path("logs")
LOG_FILE_NAME = "bot.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3


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
        scrub_sensitive_mapping(payload)
        return json.dumps(payload, ensure_ascii=False)


def _ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def _configure_file_handler() -> logging.Handler:
    log_dir = _ensure_log_dir()
    handler = RotatingFileHandler(
        log_dir / LOG_FILE_NAME,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(JsonLogFormatter())
    handler._is_sprint_json = True  # type: ignore[attr-defined]
    handler._is_sprint_json_file = True  # type: ignore[attr-defined]
    return handler


def _configure_stream_handler() -> logging.Handler:
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setLevel(logging.WARNING)
    handler.setFormatter(JsonLogFormatter())
    handler._is_sprint_json = True  # type: ignore[attr-defined]
    handler._is_sprint_json_stream = True  # type: ignore[attr-defined]
    return handler


def get_logger(name: str) -> logging.Logger:
    """Return logger configured with JSON file/stream handlers."""

    logger = logging.getLogger(name)

    if not any(
        getattr(handler, "_is_sprint_json_stream", False) for handler in logger.handlers
    ):
        logger.addHandler(_configure_stream_handler())

    if not any(
        getattr(handler, "_is_sprint_json_file", False) for handler in logger.handlers
    ):
        logger.addHandler(_configure_file_handler())

    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
