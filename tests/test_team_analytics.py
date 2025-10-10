"""Tests for team analytics service."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from services.team_analytics_service import TeamAnalyticsService


def _seed_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "team.db"
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
        base_time = datetime(2024, 5, 1, tzinfo=timezone.utc)
        payload = [
            (1, "A", (15.1, 15.2, 15.0, 15.1), 60.4),
            (2, "B", (15.5, 15.4, 15.2, 15.0), 61.1),
        ]
        for idx, (athlete_id, name, segments, total) in enumerate(payload):
            cursor = conn.execute(
                """
                INSERT INTO results (athlete_id, athlete_name, stroke, distance, total_seconds, timestamp, is_pr)
                VALUES (?,?,?,?,?,?,0)
                """,
                (
                    athlete_id,
                    name,
                    "freestyle",
                    100,
                    total,
                    (base_time.replace(day=base_time.day + idx)).isoformat(),
                ),
            )
            result_id = cursor.lastrowid
            for seg_idx, seg in enumerate(segments):
                conn.execute(
                    """
                    INSERT INTO result_segments (result_id, segment_index, split_seconds)
                    VALUES (?, ?, ?)
                    """,
                    (result_id, seg_idx, seg),
                )
        conn.commit()
    return db_path


def test_team_comparison_and_chart(tmp_path: Path) -> None:
    db_path = _seed_db(tmp_path)
    service = TeamAnalyticsService(db_path)
    comparison = service._compare_sync((1, 2), "freestyle", 100)
    assert len(comparison.athletes) == 2
    assert comparison.average_pace
    chart = service._build_chart_sync(comparison)
    assert chart.startswith(b"\x89PNG")
    summary = service.build_summary(comparison)
    assert "Team comparison" in summary
