from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from sprint_bot.application.use_cases import GetProgressUseCase, WeeklyProgressView


@dataclass
class _FakeHighlight:
    stroke: str
    distance: int
    total_seconds: float
    timestamp: datetime
    is_pr: bool


@dataclass
class _FakeProgress:
    athlete_id: int
    attempts: int
    pr_count: int
    highlights: tuple[_FakeHighlight, ...]


@pytest.mark.asyncio
async def test_maps_highlights_into_view() -> None:
    progress = _FakeProgress(
        athlete_id=7,
        attempts=3,
        pr_count=1,
        highlights=(
            _FakeHighlight(
                stroke="freestyle",
                distance=50,
                total_seconds=27.4,
                timestamp=datetime(2024, 5, 1),
                is_pr=True,
            ),
        ),
    )
    stats = AsyncMock()
    stats.weekly_progress = AsyncMock(return_value=progress)

    use_case = GetProgressUseCase(stats=stats)
    view = await use_case.execute(athlete_id=7)

    assert isinstance(view, WeeklyProgressView)
    assert view.athlete_id == 7
    assert view.attempts == 3
    assert view.pr_count == 1
    assert len(view.highlights) == 1
    assert view.highlights[0].is_pr is True


@pytest.mark.asyncio
async def test_handles_progress_without_highlights() -> None:
    stats = AsyncMock()
    stats.weekly_progress = AsyncMock(
        return_value=_FakeProgress(
            athlete_id=11, attempts=0, pr_count=0, highlights=()
        )
    )

    use_case = GetProgressUseCase(stats=stats)
    view = await use_case.execute(athlete_id=11)

    assert view.highlights == ()


@pytest.mark.asyncio
async def test_validates_athlete_id() -> None:
    use_case = GetProgressUseCase(stats=AsyncMock())
    with pytest.raises(ValueError, match="athlete_id"):
        await use_case.execute(athlete_id=0)
