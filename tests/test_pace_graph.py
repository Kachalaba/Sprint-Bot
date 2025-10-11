"""Tests for pace graph generation."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from reports.image_report import plot_pace_graph


def _prepare_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "pace.db"
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
        now = datetime(2024, 4, 1, tzinfo=timezone.utc)
        cursor = conn.execute(
            """
            INSERT INTO results (athlete_id, athlete_name, stroke, distance, total_seconds, timestamp, is_pr)
            VALUES (?,?,?,?,?,?,0)
            """,
            (1, "Graph", "freestyle", 100, 60.0, now.isoformat()),
        )
        result_id = cursor.lastrowid
        for idx, value in enumerate((15.0, 15.2, 14.9, 14.9)):
            conn.execute(
                """
                INSERT INTO result_segments (result_id, segment_index, split_seconds)
                VALUES (?, ?, ?)
                """,
                (result_id, idx, value),
            )
        conn.commit()
    return db_path


def test_plot_pace_graph_returns_png(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path)
    image = plot_pace_graph(1, "freestyle", 100, db_path=db_path)
    assert image.startswith(b"\x89PNG")
    digest = hashlib.sha256(image).hexdigest()
    assert len(digest) == 64
