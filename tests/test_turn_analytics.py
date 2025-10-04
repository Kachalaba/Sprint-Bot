import asyncio
import importlib
import importlib.util
import sqlite3
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import matplotlib
import pytest

matplotlib.use("Agg")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def progress_module() -> types.ModuleType:
    """Provide access to turn plotting helpers with safe service stubs."""

    monkeypatch = pytest.MonkeyPatch()
    stats_spec = importlib.util.spec_from_file_location(
        "services.stats_service", PROJECT_ROOT / "services" / "stats_service.py"
    )
    stats_module = importlib.util.module_from_spec(stats_spec)
    assert stats_spec.loader is not None
    stats_spec.loader.exec_module(stats_module)

    services_stub = types.ModuleType("services")
    services_stub.__path__ = [str(PROJECT_ROOT / "services")]
    services_stub.ws_athletes = SimpleNamespace(
        get_all_values=lambda: [], get_all_records=lambda: []
    )
    services_stub.ws_results = SimpleNamespace(get_all_values=lambda: [])
    monkeypatch.setitem(sys.modules, "services", services_stub)
    monkeypatch.setitem(sys.modules, "services.stats_service", stats_module)

    module = importlib.import_module("handlers.progress")
    try:
        yield module
    finally:
        monkeypatch.undo()


def test_stats_service_turn_analytics_queries(
    tmp_path: Path, progress_module: types.ModuleType
) -> None:
    StatsService = progress_module.StatsService
    StatsPeriod = progress_module.StatsPeriod
    format_turn_summary = progress_module._format_turn_summary

    async def scenario() -> None:
        db_dir = tmp_path / "turns"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / "stats.db"
        service = StatsService(db_path)
        await service.init()

        now = datetime.now(timezone.utc)
        previous_ts = (now - timedelta(days=8)).isoformat()
        current_ts = (now - timedelta(days=2)).isoformat()
        latest_ts = (now - timedelta(days=1)).isoformat()

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turn_analysis (
                    id INTEGER PRIMARY KEY,
                    result_id INTEGER NOT NULL,
                    turn_number INTEGER NOT NULL,
                    approach_time REAL,
                    wall_contact_time REAL,
                    push_off_time REAL,
                    underwater_time REAL,
                    total_turn_time REAL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO results (athlete_id, athlete_name, stroke, distance, total_seconds, timestamp, is_pr)
                VALUES (?,?,?,?,?,?,?)
                """,
                (1, "Test Swimmer", "breaststroke", 100, 70.0, previous_ts, 0),
            )
            conn.execute(
                """
                INSERT INTO results (athlete_id, athlete_name, stroke, distance, total_seconds, timestamp, is_pr)
                VALUES (?,?,?,?,?,?,?)
                """,
                (1, "Test Swimmer", "breaststroke", 100, 69.0, current_ts, 1),
            )
            conn.execute(
                """
                INSERT INTO results (athlete_id, athlete_name, stroke, distance, total_seconds, timestamp, is_pr)
                VALUES (?,?,?,?,?,?,?)
                """,
                (1, "Test Swimmer", "breaststroke", 100, 68.5, latest_ts, 1),
            )
            result_ids = [
                row[0]
                for row in conn.execute("SELECT id FROM results ORDER BY timestamp")
            ]
            turn_payload = [
                (result_ids[0], 1, 3.9, 0.75, 0.95, 3.0, 5.2),
                (result_ids[0], 2, 3.9, 0.75, 0.95, 3.0, 6.3),
                (result_ids[1], 1, 3.8, 0.7, 0.9, 2.8, 4.8),
                (result_ids[1], 2, 3.8, 0.7, 0.9, 2.8, 6.0),
                (result_ids[2], 1, 3.7, 0.68, 0.88, 2.7, 4.6),
                (result_ids[2], 2, 3.7, 0.68, 0.88, 2.7, 5.8),
            ]
            conn.executemany(
                """
                INSERT INTO turn_analysis (
                    result_id, turn_number, approach_time, wall_contact_time, push_off_time,
                    underwater_time, total_turn_time
                ) VALUES (?,?,?,?,?,?,?)
                """,
                turn_payload,
            )
            conn.commit()

        analytics = await service.get_turn_analytics(1, "breaststroke")
        rows = analytics["rows"]
        assert len(rows) == 6
        assert rows[0]["turn_number"] == 1
        assert rows[0]["timestamp"] <= rows[-1]["timestamp"]

        progress = analytics["progress"]
        assert len(progress) == 2
        first_turn = next(item for item in progress if item.turn_number == 1)
        assert first_turn.improvement_rate == pytest.approx(
            (5.2 - 4.6) / 5.2 * 100, rel=1e-3
        )
        assert first_turn.efficiency_trend < 0

        comparison = await service.compare_turn_efficiency(1, StatsPeriod.WEEK)
        assert comparison["previous"][1] == pytest.approx(5.2)
        assert comparison["current"][1] == pytest.approx((4.8 + 4.6) / 2, rel=1e-3)
        turn1 = next(
            item for item in comparison["comparisons"] if item.turn_number == 1
        )
        assert turn1.delta == pytest.approx(0.5, rel=1e-3)
        assert turn1.percent_change == pytest.approx(0.5 / 5.2 * 100, rel=1e-3)

        summary = format_turn_summary("breaststroke", progress)
        assert summary.startswith("<b>")
        assert "#1" in summary

    asyncio.run(scenario())


def test_grouping_and_plots_produce_png(
    sample_turn_rows: list[dict], progress_module: types.ModuleType
) -> None:
    group_turn_sessions = progress_module._group_turn_sessions
    build_turn_efficiency_plot = progress_module._build_turn_efficiency_plot
    build_turn_comparison_plot = progress_module._build_turn_comparison_plot
    build_turn_heatmap = progress_module._build_turn_heatmap
    TurnProgressResult = progress_module.TurnProgressResult
    format_turn_summary = progress_module._format_turn_summary

    sessions = group_turn_sessions(sample_turn_rows)
    assert len(sessions) == 2
    assert sessions[0]["turns"][0]["turn_number"] == 1
    athlete_name = sample_turn_rows[0]["athlete_name"]

    efficiency_plot = build_turn_efficiency_plot(
        sessions, athlete_name, "breaststroke"
    )
    comparison_plot = build_turn_comparison_plot(
        sessions, athlete_name, "breaststroke"
    )
    heatmap_plot = build_turn_heatmap(sessions, athlete_name, "breaststroke")

    for image in (efficiency_plot, comparison_plot, heatmap_plot):
        assert image is not None
        assert image.startswith(b"\x89PNG")

    custom_progress = (
        TurnProgressResult(turn_number=1, efficiency_trend=-0.1, improvement_rate=5.0),
        TurnProgressResult(turn_number=2, efficiency_trend=0.2, improvement_rate=-3.0),
    )
    summary = format_turn_summary("butterfly", custom_progress)
    assert summary.startswith("<b>")
    assert "#2" in summary
