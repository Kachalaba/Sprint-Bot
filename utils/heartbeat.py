"""Container heartbeat helpers used by Docker healthchecks."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from utils.logger import get_logger

DEFAULT_HEARTBEAT_PATH = Path("/app/data/.heartbeat")
DEFAULT_INTERVAL_SECONDS = 30.0
DEFAULT_STALE_AFTER_SECONDS = 120.0

logger = get_logger(__name__)


def heartbeat_path() -> Path:
    """Return path to the heartbeat file (override via ``HEARTBEAT_PATH``)."""

    raw = os.getenv("HEARTBEAT_PATH")
    return Path(raw) if raw else DEFAULT_HEARTBEAT_PATH


def heartbeat_interval() -> float:
    """Return how frequently the bot refreshes the heartbeat."""

    raw = os.getenv("HEARTBEAT_INTERVAL_SECONDS")
    if not raw:
        return DEFAULT_INTERVAL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS
    return value if value > 0 else DEFAULT_INTERVAL_SECONDS


def heartbeat_stale_after() -> float:
    """Return age (seconds) after which the heartbeat is considered stale."""

    raw = os.getenv("HEARTBEAT_STALE_SECONDS")
    if not raw:
        return DEFAULT_STALE_AFTER_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_STALE_AFTER_SECONDS
    return value if value > 0 else DEFAULT_STALE_AFTER_SECONDS


def write_heartbeat(path: Path | None = None) -> None:
    """Refresh the mtime of the heartbeat file, creating it if needed."""

    target = path or heartbeat_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    target.touch(exist_ok=True)
    os.utime(target, (now, now))


async def heartbeat_loop(
    *,
    path: Path | None = None,
    interval: float | None = None,
) -> None:
    """Periodically write the heartbeat file until the task is cancelled."""

    target = path or heartbeat_path()
    sleep_for = interval if interval and interval > 0 else heartbeat_interval()
    while True:
        try:
            write_heartbeat(target)
        except OSError as exc:
            logger.warning("heartbeat_write_failed", extra={"path": str(target), "error": str(exc)})
        await asyncio.sleep(sleep_for)


def is_heartbeat_fresh(
    *,
    path: Path | None = None,
    stale_after: float | None = None,
) -> bool:
    """Return ``True`` when the heartbeat file was updated recently enough."""

    target = path or heartbeat_path()
    threshold = stale_after if stale_after and stale_after > 0 else heartbeat_stale_after()
    try:
        mtime = target.stat().st_mtime
    except FileNotFoundError:
        return False
    return (time.time() - mtime) <= threshold


__all__ = [
    "DEFAULT_HEARTBEAT_PATH",
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_STALE_AFTER_SECONDS",
    "heartbeat_path",
    "heartbeat_interval",
    "heartbeat_stale_after",
    "heartbeat_loop",
    "is_heartbeat_fresh",
    "write_heartbeat",
]
