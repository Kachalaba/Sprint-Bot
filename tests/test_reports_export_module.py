"""Integration tests for reports export utilities."""

from __future__ import annotations

import asyncio
import csv
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reports.cache import CacheSettings, ReportCache
from reports.charts import build_progress_chart, build_segment_speed_chart
from reports.data_export import ExportFilters, export_results, load_results


def _prepare_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id INTEGER NOT NULL,
                athlete_name TEXT NOT NULL,
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
        now = datetime(2024, 5, 1, tzinfo=timezone.utc)
        for idx, total in enumerate((58.32, 57.98), start=1):
            cursor = conn.execute(
                """
                INSERT INTO results (
                    athlete_id,
                    athlete_name,
                    stroke,
                    distance,
                    total_seconds,
                    timestamp,
                    is_pr
                )
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    42,
                    "Tester",
                    "freestyle",
                    100,
                    total,
                    (now + timedelta(days=idx)).isoformat(),
                    int(idx == 2),
                ),
            )
            result_id = cursor.lastrowid
            for seg_idx, value in enumerate((14.5, 14.3, 14.7, 14.5)):
                conn.execute(
                    """
                    INSERT INTO result_segments (
                        result_id,
                        segment_index,
                        split_seconds
                    )
                    VALUES (?, ?, ?)
                    """,
                    (result_id, seg_idx, value + idx * 0.1),
                )
        conn.commit()


def test_export_results_to_csv_and_xlsx(tmp_path: Path) -> None:
    db_path = tmp_path / "results.db"
    _prepare_db(db_path)
    filters = ExportFilters(athlete_id=42, stroke="freestyle", distance=100)

    records = asyncio.run(load_results(filters, db_path=db_path))
    assert len(records) == 2
    assert records[0].athlete_name == "Tester"

    csv_bytes = asyncio.run(export_results(filters, "csv", db_path=db_path))
    rows = list(csv.reader(csv_bytes.decode("utf-8").splitlines()))
    assert rows[0][0] == "timestamp"
    assert rows[1][1] == "42"

    xlsx_bytes = asyncio.run(export_results(filters, "xlsx", db_path=db_path))
    assert xlsx_bytes.startswith(b"PK")
    assert len(xlsx_bytes) > 500

    cache_settings = CacheSettings(
        directory=tmp_path / "cache",
        ttl=timedelta(minutes=1),
    )
    cache = ReportCache(cache_settings)
    asyncio.run(cache.set("sample", "csv", csv_bytes))
    cached = asyncio.run(cache.get("sample", "csv"))
    assert cached == csv_bytes


def test_chart_generators(tmp_path: Path) -> None:
    db_path = tmp_path / "results.db"
    _prepare_db(db_path)
    filters = ExportFilters(athlete_id=42, stroke="freestyle", distance=100)
    records = asyncio.run(load_results(filters, db_path=db_path))

    speed_chart = build_segment_speed_chart(records)
    assert speed_chart.startswith(b"\x89PNG")

    progress_chart = build_progress_chart(records)
    assert progress_chart.startswith(b"\x89PNG")
