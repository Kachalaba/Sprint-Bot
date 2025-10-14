"""Contract tests for Google Sheets backed repositories using fakes."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from sprint_bot.infrastructure.storage.google_sheets import (
    GoogleSheetsStorage, _get_first, _parse_bool, _parse_date, _parse_datetime,
    _parse_duration, _parse_float, _parse_int)
from tests.fakes import SheetsClientFake


@pytest.fixture()
def sheets_storage() -> GoogleSheetsStorage:
    """Return storage initialised with in-memory worksheets."""

    client = SheetsClientFake()
    client.register_spreadsheet(
        "test",
        {
            "AthletesList": [
                {
                    "id": "athlete-001",
                    "full_name": "Alice Runner",
                    "telegram_id": 1001,
                    "is_active": True,
                    "coach_id": "coach-42",
                },
                {
                    "id": "athlete-002",
                    "full_name": "Bob Sleeper",
                    "telegram_id": 1002,
                    "is_active": False,
                    "coach_id": "coach-42",
                },
            ],
            "results": [
                {
                    "id": "race-001",
                    "athlete_id": "athlete-001",
                    "event_date": "2024-06-01",
                    "name": "Summer Sprint",
                    "distance_m": "5000",
                    "official_time": "00:18:30",
                    "coach_id": "coach-42",
                    "split1_time": "00:06:00",
                    "split1_distance": "2000",
                    "split1_segment_id": "S1",
                    "split2_time": "00:06:15",
                    "split2_distance": "2000",
                    "split3_time": "00:06:15",
                    "split3_distance": "1000",
                }
            ],
            "pr": [
                {
                    "athlete_id": "athlete-001",
                    "segment_id": "S1",
                    "best_time": "00:06:00",
                    "achieved_at": "2024-05-20 08:00:00",
                    "race_id": "race-001",
                }
            ],
            "sob": [
                {
                    "athlete_id": "athlete-001",
                    "total_time": "00:18:30",
                    "generated_at": "2024-06-02 09:00:00",
                }
            ],
        },
    )
    storage = GoogleSheetsStorage(
        spreadsheet_key="test",
        credentials_path=Path("/tmp/credentials.json"),
    )
    storage._client = client  # type: ignore[attr-defined]
    storage._spreadsheet = client.open_by_key("test")  # type: ignore[attr-defined]
    return storage


@pytest.mark.asyncio()
async def test_athletes_repo_filters_active_only(
    sheets_storage: GoogleSheetsStorage,
) -> None:
    repo = sheets_storage.athletes
    athletes = await repo.list_active()
    assert len(athletes) == 1
    assert athletes[0].id == "athlete-001"

    by_telegram = await repo.get_by_telegram(1001)
    assert by_telegram is not None
    assert by_telegram.full_name == "Alice Runner"
    assert by_telegram.coach_id == "coach-42"


@pytest.mark.asyncio()
async def test_results_repo_parses_splits(sheets_storage: GoogleSheetsStorage) -> None:
    repo = sheets_storage.results
    races = await repo.list_recent(limit=1)
    assert len(races) == 1

    race = races[0]
    assert race.id == "race-001"
    assert race.distance_meters == 5000
    assert race.official_time and race.official_time.total_seconds() == pytest.approx(
        1110
    )
    assert len(race.splits) == 3
    assert race.splits[0].segment_id == "S1"
    assert race.splits[0].elapsed.total_seconds() == pytest.approx(360)


@pytest.mark.asyncio()
async def test_records_repo_returns_sob(sheets_storage: GoogleSheetsStorage) -> None:
    repo = sheets_storage.records
    prs = await repo.list_segment_prs("athlete-001")
    assert prs
    assert prs[0].segment_id == "S1"

    sob = await repo.get_sob("athlete-001")
    assert sob is not None
    assert sob.total_time.total_seconds() == pytest.approx(1110)
    assert sob.generated_at.date() == datetime(2024, 6, 2).date()


@pytest.mark.asyncio()
async def test_storage_fetch_helpers(sheets_storage: GoogleSheetsStorage) -> None:
    assert await sheets_storage.fetch_records("missing") == []
    values = await sheets_storage.fetch_values("results")
    assert values and values[0]


def test_parse_helpers_cover_edge_cases() -> None:
    assert _parse_bool("yes", False) is True
    assert _parse_bool("inactive", True) is False
    assert _parse_bool(None, False) is False

    assert _parse_int("42") == 42
    assert _parse_int(" ") is None

    assert _parse_float("3,5") == pytest.approx(3.5)
    assert _parse_float("invalid") is None

    assert _parse_date("2024-06-01") == date(2024, 6, 1)
    assert _parse_date("01/06/2024") == date(2024, 6, 1)
    assert _parse_date("bad") is None

    target_dt = datetime(2024, 6, 1, 8, 0, 0)
    assert _parse_datetime("2024-06-01T08:00:00") == target_dt
    assert _parse_datetime("01.06.2024 08:00") == datetime(2024, 6, 1, 8, 0)
    assert _parse_datetime("bad") is None

    assert _parse_duration("75s") == timedelta(seconds=75)
    assert _parse_duration("1:02:03") == timedelta(hours=1, minutes=2, seconds=3)
    assert _parse_duration("04:30") == timedelta(minutes=4, seconds=30)
    assert _parse_duration("bad") is None

    assert _get_first({"a": 1, "b": 2}, "x", "a") == 1
    assert _get_first({"x": "", "y": None}, "x", "y") is None
