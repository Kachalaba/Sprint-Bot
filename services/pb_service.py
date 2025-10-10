"""Utilities for calculating segment personal bests and Sum of Best (SoB)."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from services.stats_service import SobStats, calc_sob
from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_DB_PATH = Path("data/results.db")

_SEGMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS result_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id INTEGER NOT NULL,
    segment_index INTEGER NOT NULL,
    split_seconds REAL NOT NULL,
    FOREIGN KEY(result_id) REFERENCES results(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_result_segments_result
    ON result_segments(result_id);
CREATE INDEX IF NOT EXISTS idx_result_segments_lookup
    ON result_segments(result_id, segment_index);
"""


@dataclass(frozen=True, slots=True)
class AttemptSplits:
    """Describes segment times of a single recorded attempt."""

    total: float
    segments: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SobResult:
    """Container describing Sum of Best calculation."""

    segments: tuple[float, ...]
    total: float | None


@dataclass(frozen=True, slots=True)
class SegmentComparison:
    """Describe comparison between latest split and previous personal best."""

    index: int
    current: float
    previous_best: float | None
    improved: bool


@dataclass(frozen=True, slots=True)
class ComparisonSummary:
    """Summary comparing latest result with previous records."""

    total_previous: float | None
    total_current: float
    total_improved: bool
    segments: tuple[SegmentComparison, ...]
    sob: SobStats


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.executescript(_SEGMENT_SCHEMA)
    return conn


def _fetch_latest_result(
    conn: sqlite3.Connection,
    athlete_id: int,
    stroke: str,
    distance: int,
) -> tuple[sqlite3.Row, tuple[tuple[int, float], ...]] | None:
    row = conn.execute(
        """
        SELECT id, total_seconds
        FROM results
        WHERE athlete_id = ? AND stroke = ? AND distance = ?
        ORDER BY timestamp DESC, id DESC
        LIMIT 1
        """,
        (athlete_id, stroke, distance),
    ).fetchone()
    if row is None:
        return None
    segments = conn.execute(
        """
        SELECT segment_index, split_seconds
        FROM result_segments
        WHERE result_id = ?
        ORDER BY segment_index
        """,
        (row["id"],),
    ).fetchall()
    if not segments:
        return None
    return row, tuple((int(item[0]), float(item[1])) for item in segments)


def get_latest_attempt(
    athlete_id: int,
    stroke: str,
    distance: int,
    *,
    db_path: Path = DEFAULT_DB_PATH,
) -> AttemptSplits | None:
    """Return latest attempt splits for provided athlete."""

    stroke = stroke.strip().lower()
    try:
        with _connect(db_path) as conn:
            latest = _fetch_latest_result(conn, athlete_id, stroke, distance)
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        logger.error("Failed to fetch latest attempt: %s", exc)
        return None
    if latest is None:
        return None
    row, segments = latest
    ordered = tuple(value for _, value in segments)
    return AttemptSplits(total=float(row["total_seconds"]), segments=ordered)


def _fetch_total_pb(
    conn: sqlite3.Connection,
    athlete_id: int,
    stroke: str,
    distance: int,
    *,
    exclude_result: int | None = None,
) -> tuple[sqlite3.Row, tuple[tuple[int, float], ...]] | None:
    args: list[object] = [athlete_id, stroke, distance]
    exclude_clause = ""
    if exclude_result is not None:
        exclude_clause = "AND id != ?"
        args.append(exclude_result)
    row = conn.execute(
        f"""
        SELECT id, total_seconds
        FROM results
        WHERE athlete_id = ? AND stroke = ? AND distance = ? {exclude_clause}
        ORDER BY total_seconds ASC, timestamp DESC, id DESC
        LIMIT 1
        """,
        tuple(args),
    ).fetchone()
    if row is None:
        return None
    segments = conn.execute(
        """
        SELECT segment_index, split_seconds
        FROM result_segments
        WHERE result_id = ?
        ORDER BY segment_index
        """,
        (row["id"],),
    ).fetchall()
    if not segments:
        return None
    return row, tuple((int(item[0]), float(item[1])) for item in segments)


def get_total_pb_attempt(
    athlete_id: int,
    stroke: str,
    distance: int,
    *,
    db_path: Path = DEFAULT_DB_PATH,
) -> AttemptSplits | None:
    """Return best total attempt splits for athlete."""

    stroke = stroke.strip().lower()
    try:
        with _connect(db_path) as conn:
            result = _fetch_total_pb(conn, athlete_id, stroke, distance)
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        logger.error("Failed to fetch total PB attempt: %s", exc)
        return None
    if result is None:
        return None
    row, segments = result
    return AttemptSplits(
        total=float(row["total_seconds"]),
        segments=tuple(value for _, value in segments),
    )


def _fetch_segment_bests(
    conn: sqlite3.Connection,
    athlete_id: int,
    stroke: str,
    distance: int,
    *,
    exclude_result: int | None = None,
) -> dict[int, float]:
    args: list[object] = [athlete_id, stroke, distance]
    exclude_clause = ""
    if exclude_result is not None:
        exclude_clause = "AND results.id != ?"
        args.append(exclude_result)
    rows = conn.execute(
        f"""
        SELECT result_segments.segment_index AS idx,
               MIN(result_segments.split_seconds) AS best
        FROM result_segments
        INNER JOIN results ON results.id = result_segments.result_id
        WHERE results.athlete_id = ?
          AND results.stroke = ?
          AND results.distance = ?
          {exclude_clause}
        GROUP BY result_segments.segment_index
        ORDER BY result_segments.segment_index
        """,
        tuple(args),
    ).fetchall()
    return {
        int(row["idx"]): float(row["best"]) for row in rows if row["best"] is not None
    }


def get_segment_pb(
    athlete_id: int,
    stroke: str,
    segment_index: int,
    *,
    distance: int | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> float | None:
    """Return best split for the specified athlete and segment."""

    if segment_index < 0:
        raise ValueError("segment_index must be non-negative")
    stroke = stroke.strip().lower()
    try:
        with _connect(db_path) as conn:
            if distance is None:
                row = conn.execute(
                    """
                    SELECT MIN(result_segments.split_seconds) AS best
                    FROM result_segments
                    INNER JOIN results ON results.id = result_segments.result_id
                    WHERE results.athlete_id = ? AND results.stroke = ?
                          AND result_segments.segment_index = ?
                    """,
                    (athlete_id, stroke, segment_index),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT MIN(result_segments.split_seconds) AS best
                    FROM result_segments
                    INNER JOIN results ON results.id = result_segments.result_id
                    WHERE results.athlete_id = ? AND results.stroke = ?
                      AND results.distance = ?
                      AND result_segments.segment_index = ?
                    """,
                    (athlete_id, stroke, distance, segment_index),
                ).fetchone()
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        logger.error("Failed to fetch segment PB: %s", exc)
        return None
    if not row or row["best"] is None:
        return None
    return float(row["best"])


def get_sob(
    athlete_id: int,
    stroke: str,
    distance: int,
    *,
    db_path: Path = DEFAULT_DB_PATH,
) -> SobResult:
    """Return Sum of Best segments and total for the athlete."""

    stroke = stroke.strip().lower()
    try:
        with _connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT result_segments.segment_index AS idx,
                       MIN(result_segments.split_seconds) AS best
                FROM result_segments
                INNER JOIN results ON results.id = result_segments.result_id
                WHERE results.athlete_id = ?
                  AND results.stroke = ?
                  AND results.distance = ?
                GROUP BY result_segments.segment_index
                ORDER BY result_segments.segment_index
                """,
                (athlete_id, stroke, distance),
            ).fetchall()
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        logger.error("Failed to calculate SoB: %s", exc)
        rows = []
    if not rows:
        return SobResult(segments=(), total=None)
    segments = tuple(float(row["best"]) for row in rows if row["best"] is not None)
    total = sum(segments) if segments else None
    return SobResult(segments=segments, total=total)


def compare_last_with_pb(
    athlete_id: int,
    stroke: str,
    distance: int,
    *,
    db_path: Path = DEFAULT_DB_PATH,
) -> ComparisonSummary | None:
    """Compare latest result with previous personal and segment bests."""

    stroke = stroke.strip().lower()
    try:
        with _connect(db_path) as conn:
            latest = _fetch_latest_result(conn, athlete_id, stroke, distance)
            if latest is None:
                return None
            latest_row, latest_segments = latest
            previous_total_row = _fetch_total_pb(
                conn, athlete_id, stroke, distance, exclude_result=latest_row["id"]
            )
            previous_total = (
                float(previous_total_row[0]["total_seconds"])
                if previous_total_row is not None
                else None
            )
            previous_segment_bests = _fetch_segment_bests(
                conn, athlete_id, stroke, distance, exclude_result=latest_row["id"]
            )
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        logger.error("Failed to compare result with PB: %s", exc)
        return None

    latest_map = {idx: value for idx, value in latest_segments}
    indices = sorted(latest_map)
    latest_sequence: list[float] = []
    previous_sequence: list[Optional[float]] = []
    segment_comparisons: list[SegmentComparison] = []
    for idx in indices:
        current_value = latest_map[idx]
        previous_best = previous_segment_bests.get(idx)
        improved = previous_best is None or current_value < previous_best
        latest_sequence.append(current_value)
        previous_sequence.append(previous_best)
        segment_comparisons.append(
            SegmentComparison(
                index=idx,
                current=current_value,
                previous_best=previous_best,
                improved=improved,
            )
        )

    sob_stats = calc_sob(previous_sequence, latest_sequence)
    total_current = float(latest_row["total_seconds"])
    total_improved = previous_total is None or total_current < previous_total

    return ComparisonSummary(
        total_previous=previous_total,
        total_current=total_current,
        total_improved=total_improved,
        segments=tuple(segment_comparisons),
        sob=sob_stats,
    )


async def async_compare_last_with_pb(
    athlete_id: int,
    stroke: str,
    distance: int,
    *,
    db_path: Path = DEFAULT_DB_PATH,
) -> ComparisonSummary | None:
    """Async wrapper around :func:`compare_last_with_pb`."""

    return await asyncio.to_thread(
        compare_last_with_pb, athlete_id, stroke, distance, db_path=db_path
    )


__all__ = [
    "AttemptSplits",
    "ComparisonSummary",
    "SegmentComparison",
    "SobResult",
    "async_compare_last_with_pb",
    "compare_last_with_pb",
    "get_latest_attempt",
    "get_segment_pb",
    "get_sob",
    "get_total_pb_attempt",
]
