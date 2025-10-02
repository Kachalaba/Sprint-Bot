from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from services.io_service import IOService


def _seed_results(db_path: Path) -> None:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO results (
                athlete_id,
                athlete_name,
                stroke,
                distance,
                total_seconds,
                timestamp,
                is_pr
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                101,
                "Test Athlete",
                "freestyle",
                100,
                62.5,
                datetime(2024, 3, 1, 8, 0).isoformat(),
                1,
            ),
        )
        conn.commit()


def test_export_contains_bom_and_header(tmp_path: Path) -> None:
    async def scenario() -> None:
        db_path = tmp_path / "results.db"
        service = IOService(db_path)
        await service.init()
        _seed_results(db_path)

        data = await service.export_results(athlete_ids=(101,))

        assert data.startswith(b"\xef\xbb\xbf")
        text = data.decode("utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]
        assert (
            lines[0]
            == "athlete_id,athlete_name,stroke,distance,total_seconds,timestamp,is_pr"
        )
        assert any("Test Athlete" in line for line in lines[1:])

    asyncio.run(scenario())


def test_dry_run_reports_invalid_rows(tmp_path: Path) -> None:
    async def scenario() -> None:
        db_path = tmp_path / "results.db"
        service = IOService(db_path)
        await service.init()

        csv_content = (
            "athlete_id,stroke,distance,time,timestamp,is_pr\n"
            ",freestyle,100,1:10.00,2024-03-01T08:00:00,1\n"
            "102,,100,1:11.00,2024-03-01T08:05:00,0\n"
            "103,butterfly,50,1:05.5,2024-03-01T09:00:00,1\n"
        )

        preview = await service.dry_run_import(csv_content.encode("utf-8"))

        assert preview.total_rows == 3
        assert len(preview.rows) == 1
        assert len(preview.issues) == 2
        messages = {issue.message for issue in preview.issues}
        assert "athlete_id is required" in messages
        assert "stroke is required" in messages

    asyncio.run(scenario())


def test_apply_import_is_idempotent(tmp_path: Path) -> None:
    async def scenario() -> None:
        db_path = tmp_path / "results.db"
        service = IOService(db_path)
        await service.init()

        csv_content = (
            "athlete_id,stroke,distance,time,timestamp,is_pr\n"
            "101,freestyle,100,1:10.00,2024-03-01T08:00:00,1\n"
            "102,butterfly,50,33.50,2024-03-01T08:05:00,0\n"
        )

        preview = await service.dry_run_import(csv_content.encode("utf-8"))
        assert len(preview.rows) == 2

        result = await service.apply_import(preview)
        assert result.inserted == 2
        assert result.skipped == 0

        second_preview = await service.dry_run_import(csv_content.encode("utf-8"))
        assert len(second_preview.rows) == 0
        assert any("duplicate result" in issue.message for issue in second_preview.issues)

    asyncio.run(scenario())

