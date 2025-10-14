"""File-system based cache for heavy report artefacts."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Final

__all__ = ["CacheSettings", "ReportCache", "normalise_extension"]


@dataclass(frozen=True, slots=True)
class CacheSettings:
    """Configuration for report cache behaviour."""

    directory: Path
    ttl: timedelta


_DEFAULT_CACHE_DIR: Final[Path] = Path("data/cache/reports")
_DEFAULT_TTL: Final[timedelta] = timedelta(minutes=30)


def normalise_extension(extension: str) -> str:
    """Return normalised extension without leading dot."""

    ext = extension.strip().lower()
    if ext.startswith("."):
        ext = ext[1:]
    if not ext:
        raise ValueError("extension must not be empty")
    return ext


class ReportCache:
    """Persist report artefacts on disk with TTL-based invalidation."""

    def __init__(
        self,
        settings: CacheSettings | None = None,
    ) -> None:
        self._settings = settings or CacheSettings(
            directory=_DEFAULT_CACHE_DIR,
            ttl=_DEFAULT_TTL,
        )
        self._lock = asyncio.Lock()
        self._settings.directory.mkdir(parents=True, exist_ok=True)

    def _hash_key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return digest

    def _path_for(self, key: str, extension: str) -> Path:
        ext = normalise_extension(extension)
        filename = f"{self._hash_key(key)}.{ext}"
        return self._settings.directory / filename

    async def get(self, key: str, extension: str) -> bytes | None:
        """Return cached bytes if entry exists and not expired."""

        path = self._path_for(key, extension)
        return await asyncio.to_thread(self._read_if_fresh, path)

    def _read_if_fresh(self, path: Path) -> bytes | None:
        if not path.exists():
            return None
        ttl_seconds = int(self._settings.ttl.total_seconds())
        if ttl_seconds > 0:
            mtime = path.stat().st_mtime
            if time.time() - mtime > ttl_seconds:
                with contextlib.suppress(OSError):
                    path.unlink()
                return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    async def set(self, key: str, extension: str, data: bytes) -> Path:
        """Persist artefact and return its path."""

        path = self._path_for(key, extension)
        async with self._lock:
            await asyncio.to_thread(self._write_file, path, data)
        return path

    def _write_file(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_path, path)

    async def purge_expired(self) -> None:
        """Delete expired cache entries in the background."""

        await asyncio.to_thread(self._purge_sync)

    def _purge_sync(self) -> None:
        ttl_seconds = int(self._settings.ttl.total_seconds())
        if ttl_seconds <= 0:
            return
        now = time.time()
        for path in self._settings.directory.glob("*"):
            if not path.is_file():
                continue
            try:
                if now - path.stat().st_mtime > ttl_seconds:
                    path.unlink()
            except OSError:
                continue
