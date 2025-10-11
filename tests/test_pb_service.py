"""Tests for PB and SoB calculation service."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from services.pb_service import (
    compare_last_with_pb,
    get_latest_attempt,
    get_segment_pb,
    get_sob,
    get_total_pb_attempt,
)


def _setup_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "results.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id INTEGER NOT NULL,
                athlete_name TEXT NOT NULL DEFAULT '',
                stroke TEXT NOT NULL,
                distance INTEGER NOT NULL,
                total_seconds REAL NOT NULL,
                timestamp TEXT NOT NULL,
                is_pr INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE result_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id INTEGER NOT NULL,
                segment_index INTEGER NOT NULL,
                split_seconds REAL NOT NULL
            );
            """
        )
    return db_path


def _insert_result(
    db_path: Path,
    *,
    athlete_id: int,
    athlete_name: str,
    stroke: str,
    distance: int,
    total: float,
    segments: tuple[float, ...],
    ts: datetime,
) -> None:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO results (athlete_id, athlete_name, stroke, distance, total_seconds, timestamp, is_pr)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (athlete_id, athlete_name, stroke, distance, total, ts.isoformat()),
        )
        result_id = cursor.lastrowid
        for idx, value in enumerate(segments):
            conn.execute(
                """
                INSERT INTO result_segments (result_id, segment_index, split_seconds)
                VALUES (?, ?, ?)
                """,
                (result_id, idx, value),
            )
        conn.commit()


def test_get_segment_pb_returns_fastest_split(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    now = datetime.now(timezone.utc)
    _insert_result(
        db_path,
        athlete_id=7,
        athlete_name="Test",
        stroke="freestyle",
        distance=100,
        total=63.2,
        segments=(15.5, 15.7, 16.0, 16.0),
        ts=now,
    )
    _insert_result(
        db_path,
        athlete_id=7,
        athlete_name="Test",
        stroke="freestyle",
        distance=100,
        total=62.8,
        segments=(15.2, 15.6, 16.0, 16.0),
        ts=now.replace(day=now.day + 1),
    )

    pb = get_segment_pb(7, "freestyle", 0, distance=100, db_path=db_path)
    assert pb == 15.2


def test_get_sob_and_compare_last(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    now = datetime.now(timezone.utc)
    _insert_result(
        db_path,
        athlete_id=3,
        athlete_name="Alpha",
        stroke="butterfly",
        distance=100,
        total=65.0,
        segments=(16.2, 16.1, 16.4, 16.3),
        ts=now,
    )
    _insert_result(
        db_path,
        athlete_id=3,
        athlete_name="Alpha",
        stroke="butterfly",
        distance=100,
        total=64.5,
        segments=(16.0, 15.9, 16.3, 16.3),
        ts=now.replace(day=now.day + 1),
    )

    sob = get_sob(3, "butterfly", 100, db_path=db_path)
    assert sob.total is not None
    assert sob.total < 65.0
    comparison = compare_last_with_pb(3, "butterfly", 100, db_path=db_path)
    assert comparison is not None
    assert comparison.total_improved is True
    assert any(item.improved for item in comparison.segments)


def test_latest_and_total_attempt_helpers(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    now = datetime.now(timezone.utc)
    _insert_result(
        db_path,
        athlete_id=2,
        athlete_name="Beta",
        stroke="freestyle",
        distance=50,
        total=25.0,
        segments=(6.2, 6.3, 6.2, 6.3),
        ts=now,
    )
    attempt = get_latest_attempt(2, "freestyle", 50, db_path=db_path)
    assert attempt is not None
    assert attempt.total == 25.0
    pb_attempt = get_total_pb_attempt(2, "freestyle", 50, db_path=db_path)
    assert pb_attempt is not None
    assert pb_attempt.segments[0] == 6.2
