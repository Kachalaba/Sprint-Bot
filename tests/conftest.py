from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.turn_service import TurnService

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")


@pytest.fixture
def sample_turn_rows() -> list[dict]:
    """Return synthetic turn analysis rows for plotting and analytics tests."""

    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows: list[dict] = []
    result_ids = (101, 102)
    offsets = (timedelta(days=0), timedelta(days=1))
    for result_id, offset in zip(result_ids, offsets):
        timestamp = base_time + offset
        for turn_number, total in enumerate((5.2, 4.8), start=1):
            rows.append(
                {
                    "result_id": result_id,
                    "timestamp": timestamp,
                    "distance": 100,
                    "stroke": "breaststroke",
                    "athlete_name": "Test Swimmer",
                    "turn_number": turn_number,
                    "approach_time": 3.9,
                    "wall_contact_time": 0.75,
                    "push_off_time": 0.95,
                    "underwater_time": 3.0,
                    "total_turn_time": total + turn_number * 0.1,
                }
            )
    return rows


@pytest.fixture
def mock_turn_service() -> AsyncMock:
    """Return AsyncMock-based mock for :class:`TurnService`."""

    return AsyncMock(spec=TurnService)
