"""Bounded TTL cache for the most recent result of each (coach, athlete) pair.

Replaces the historical ``LAST_RESULTS`` module-level dict, which had no
expiration and grew unbounded for the lifetime of the process.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Iterator, Mapping, MutableMapping, Tuple

CacheKey = Tuple[int, int]
CachePayload = MutableMapping[str, Any]


class LastResultsCache:
    """Thread-safe bounded TTL cache keyed by (coach_id, athlete_id)."""

    DEFAULT_TTL_SECONDS = 3600.0
    DEFAULT_MAX_ENTRIES = 256

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: callable = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl = float(ttl_seconds)
        self._max_entries = int(max_entries)
        self._clock = clock
        self._store: OrderedDict[CacheKey, tuple[float, CachePayload]] = OrderedDict()
        self._lock = threading.RLock()

    def __len__(self) -> int:
        with self._lock:
            self._evict_expired_locked(self._clock())
            return len(self._store)

    def set(self, key: CacheKey, payload: Mapping[str, Any]) -> None:
        """Store a fresh payload, evicting oldest entries when necessary."""

        if not isinstance(key, tuple) or len(key) != 2:
            raise ValueError("key must be a (coach_id, athlete_id) tuple")
        with self._lock:
            now = self._clock()
            self._evict_expired_locked(now)
            self._store[key] = (now, dict(payload))
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def get(self, key: CacheKey) -> CachePayload | None:
        """Return a payload if present and not expired, else ``None``."""

        with self._lock:
            now = self._clock()
            self._evict_expired_locked(now)
            entry = self._store.get(key)
            if entry is None:
                return None
            self._store.move_to_end(key)
            return entry[1]

    def update_comment_by_timestamp(self, timestamp: str, comment: str) -> int:
        """Update the cached comment for every entry matching ``timestamp``.

        Returns the number of entries that were updated.
        """

        updated = 0
        with self._lock:
            now = self._clock()
            self._evict_expired_locked(now)
            for entry_timestamp, payload in self._iter_payloads_locked():
                if entry_timestamp == timestamp:
                    payload["comment"] = comment
                    updated += 1
        return updated

    def discard(self, key: CacheKey) -> None:
        """Remove ``key`` from the cache (no-op if absent)."""

        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Drop every cached entry."""

        with self._lock:
            self._store.clear()

    def _iter_payloads_locked(self) -> Iterator[tuple[str | None, CachePayload]]:
        for _, payload in self._store.values():
            yield payload.get("timestamp"), payload

    def _evict_expired_locked(self, now: float) -> None:
        cutoff = now - self._ttl
        expired: list[CacheKey] = []
        for key, (stored_at, _) in self._store.items():
            if stored_at < cutoff:
                expired.append(key)
            else:
                break
        for key in expired:
            self._store.pop(key, None)


__all__ = ["CacheKey", "CachePayload", "LastResultsCache"]
