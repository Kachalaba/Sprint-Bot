"""Utilities for analysing sprint progress and personal records.

The leaderboard metric is the number of new personal records (PR) achieved
within the requested period. This keeps the implementation lightweight and
ensures the ranking can be computed directly from the stored attempts without
reconstructing historical deltas.
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class TotalPRResult:
    """Information about overall personal record status."""

    previous: float | None
    current: float
    is_new: bool
    delta: float


@dataclass(frozen=True)
class SobStats:
    """Describe Sum of Best calculations for a result."""

    previous: float | None
    current: float
    delta: float


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    """Single leaderboard row for a period."""

    athlete_id: int
    athlete_name: str
    pr_count: int
    attempts: int


@dataclass(frozen=True, slots=True)
class ProgressResult:
    """Highlight attempt used in personal progress summaries."""

    stroke: str
    distance: int
    total_seconds: float
    timestamp: datetime
    is_pr: bool


@dataclass(frozen=True, slots=True)
class WeeklyProgress:
    """Personal summary for the last week."""

    athlete_id: int
    attempts: int
    pr_count: int
    highlights: tuple[ProgressResult, ...]


class StatsPeriod(str, Enum):
    """Supported leaderboard periods."""

    WEEK = "week"
    MONTH = "month"


class StatsService:
    """Aggregate sprint statistics from SQLite storage."""

    _SETUP_SQL = """
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        athlete_id INTEGER NOT NULL,
        athlete_name TEXT NOT NULL DEFAULT '',
        stroke TEXT NOT NULL,
        distance INTEGER NOT NULL,
        total_seconds REAL NOT NULL,
        timestamp TEXT NOT NULL,
        is_pr INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_stats_timestamp ON results(timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_stats_athlete ON results(athlete_id);
    """

    def __init__(self, db_path: Path | str = Path("data/results.db")) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        """Ensure table required for stats exists."""

        async with self._lock:
            await asyncio.to_thread(self._ensure_schema)

    async def leaderboard(
        self,
        period: StatsPeriod,
        *,
        limit: int = 10,
        now: datetime | None = None,
    ) -> tuple[LeaderboardEntry, ...]:
        """Return leaderboard entries for the given period."""

        since = self._period_start(period, now=now)
        rows = await asyncio.to_thread(self._fetch_leaderboard, since, limit)
        return tuple(rows)

    async def weekly_progress(
        self,
        athlete_id: int,
        *,
        limit: int = 3,
        now: datetime | None = None,
    ) -> WeeklyProgress:
        """Return attempts, PR count and highlights for the last 7 days."""

        since = self._period_start(StatsPeriod.WEEK, now=now)
        attempts_task = asyncio.create_task(
            asyncio.to_thread(self._count_attempts, athlete_id, since)
        )
        prs_task = asyncio.create_task(
            asyncio.to_thread(self._count_prs, athlete_id, since)
        )
        highlights_task = asyncio.create_task(
            asyncio.to_thread(self._fetch_highlights, athlete_id, since, limit)
        )
        attempts, pr_count, highlights = await asyncio.gather(
            attempts_task, prs_task, highlights_task
        )
        return WeeklyProgress(
            athlete_id=athlete_id,
            attempts=attempts,
            pr_count=pr_count,
            highlights=tuple(highlights),
        )

    # --- calculation helpers -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(self._SETUP_SQL)
            conn.commit()

    @staticmethod
    def _period_start(period: StatsPeriod, *, now: datetime | None) -> datetime:
        current = now or datetime.now(timezone.utc)
        if period is StatsPeriod.MONTH:
            delta = timedelta(days=30)
        else:
            delta = timedelta(days=7)
        return current - delta

    def _fetch_leaderboard(
        self, since: datetime, limit: int
    ) -> Iterable[LeaderboardEntry]:
        query = """
            SELECT
                athlete_id AS athlete_id,
                COALESCE(NULLIF(TRIM(athlete_name), ''), 'ID ' || athlete_id) AS name,
                SUM(CASE WHEN is_pr = 1 THEN 1 ELSE 0 END) AS pr_count,
                COUNT(*) AS attempts
            FROM results
            WHERE timestamp >= ?
            GROUP BY athlete_id
            HAVING SUM(CASE WHEN is_pr = 1 THEN 1 ELSE 0 END) > 0
            ORDER BY pr_count DESC, attempts DESC, name COLLATE NOCASE ASC
            LIMIT ?
        """
        args = (since.isoformat(), limit)
        with self._connect() as conn:
            cursor = conn.execute(query, args)
            rows = cursor.fetchall()
        for row in rows:
            yield LeaderboardEntry(
                athlete_id=int(row["athlete_id"]),
                athlete_name=str(row["name"] or f"ID {row['athlete_id']}").strip(),
                pr_count=int(row["pr_count"] or 0),
                attempts=int(row["attempts"] or 0),
            )

    def _count_attempts(self, athlete_id: int, since: datetime) -> int:
        query = """
            SELECT COUNT(*)
            FROM results
            WHERE athlete_id = ? AND timestamp >= ?
        """
        with self._connect() as conn:
            cursor = conn.execute(query, (athlete_id, since.isoformat()))
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def _count_prs(self, athlete_id: int, since: datetime) -> int:
        query = """
            SELECT COUNT(*)
            FROM results
            WHERE athlete_id = ? AND timestamp >= ? AND is_pr = 1
        """
        with self._connect() as conn:
            cursor = conn.execute(query, (athlete_id, since.isoformat()))
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def _fetch_highlights(
        self, athlete_id: int, since: datetime, limit: int
    ) -> Iterable[ProgressResult]:
        query = """
            SELECT stroke, distance, total_seconds, timestamp, is_pr
            FROM results
            WHERE athlete_id = ? AND timestamp >= ?
            ORDER BY is_pr DESC, total_seconds ASC, timestamp DESC
            LIMIT ?
        """
        args = (athlete_id, since.isoformat(), limit)
        with self._connect() as conn:
            cursor = conn.execute(query, args)
            rows = cursor.fetchall()
        results: list[ProgressResult] = []
        for row in rows:
            ts_raw = row["timestamp"]
            timestamp = self._parse_timestamp(ts_raw)
            results.append(
                ProgressResult(
                    stroke=str(row["stroke"]),
                    distance=int(row["distance"]),
                    total_seconds=float(row["total_seconds"]),
                    timestamp=timestamp,
                    is_pr=bool(row["is_pr"]),
                )
            )
        return results

    @staticmethod
    def _parse_timestamp(raw: str | bytes | None) -> datetime:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        text = (raw or "").strip()
        if not text:
            raise ValueError("timestamp column cannot be empty")
        try:
            return datetime.fromisoformat(text)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise ValueError(f"invalid timestamp format: {text!r}") from exc


def calc_total_pr(previous_best: float | None, current_total: float) -> TotalPRResult:
    """Return total PR status comparing new total with the previous best."""

    is_new = previous_best is None or current_total < previous_best
    if is_new and previous_best is not None:
        delta = previous_best - current_total
    else:
        delta = 0.0
    return TotalPRResult(
        previous=previous_best,
        current=current_total,
        is_new=is_new,
        delta=delta,
    )


def calc_segment_prs(
    previous_bests: Sequence[float | None],
    new_segments: Sequence[float],
) -> list[bool]:
    """Return list of flags showing which segments improved."""

    results: list[bool] = []
    for idx, segment in enumerate(new_segments):
        prev = previous_bests[idx] if idx < len(previous_bests) else None
        results.append(prev is None or segment < prev)
    return results


def calc_sob(
    previous_bests: Sequence[float | None],
    new_segments: Sequence[float],
) -> SobStats:
    """Calculate Sum of Best metrics for provided segment times."""

    prev_values = [value for value in previous_bests if value is not None]
    previous = sum(prev_values) if prev_values else None
    max_len = max(len(previous_bests), len(new_segments))
    current_total = 0.0
    for idx in range(max_len):
        prev = previous_bests[idx] if idx < len(previous_bests) else None
        new = new_segments[idx] if idx < len(new_segments) else None
        if prev is None and new is None:
            continue
        if prev is None:
            best = new if new is not None else 0.0
        elif new is None:
            best = prev
        else:
            best = min(prev, new)
        current_total += best
    if previous is None:
        delta = 0.0
    else:
        delta = max(previous - current_total, 0.0)
    return SobStats(previous=previous, current=current_total, delta=delta)


__all__ = [
    "LeaderboardEntry",
    "ProgressResult",
    "SobStats",
    "StatsPeriod",
    "StatsService",
    "TotalPRResult",
    "WeeklyProgress",
    "calc_segment_prs",
    "calc_sob",
    "calc_total_pr",
]
