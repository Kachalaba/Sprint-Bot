from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest

from sprint_bot.application.use_cases import GetPRsAndSOBUseCase


@dataclass
class _FakeSegment:
    index: int
    current: float
    previous_best: float | None
    improved: bool


@dataclass
class _FakeSob:
    total: float | None
    segments: tuple[float, ...]


@dataclass
class _FakeSummary:
    total_previous: float | None
    total_current: float
    total_improved: bool
    segments: tuple[_FakeSegment, ...]
    sob: _FakeSob


@pytest.mark.asyncio
async def test_returns_view_with_segments_and_sob() -> None:
    summary = _FakeSummary(
        total_previous=60.5,
        total_current=58.2,
        total_improved=True,
        segments=(
            _FakeSegment(0, 28.0, 29.0, True),
            _FakeSegment(1, 30.2, 31.0, True),
        ),
        sob=_FakeSob(total=57.8, segments=(28.0, 29.8)),
    )
    pb = AsyncMock()
    pb.compare_last_with_pb = AsyncMock(return_value=summary)

    use_case = GetPRsAndSOBUseCase(pb=pb)
    view = await use_case.execute(athlete_id=1, stroke="free", distance=100)

    assert view is not None
    assert view.total_improved
    assert view.total_previous_seconds == 60.5
    assert view.sob_total_seconds == 57.8
    assert view.sob_segment_count == 2
    assert len(view.segments) == 2
    assert view.segments[0].improved is True
    assert view.segments[0].previous_best_seconds == 29.0


@pytest.mark.asyncio
async def test_returns_none_when_no_summary() -> None:
    pb = AsyncMock()
    pb.compare_last_with_pb = AsyncMock(return_value=None)

    use_case = GetPRsAndSOBUseCase(pb=pb)
    view = await use_case.execute(athlete_id=1, stroke="free", distance=100)

    assert view is None


@pytest.mark.asyncio
async def test_validates_inputs() -> None:
    use_case = GetPRsAndSOBUseCase(pb=AsyncMock())
    with pytest.raises(ValueError, match="athlete_id"):
        await use_case.execute(athlete_id=0, stroke="free", distance=50)
    with pytest.raises(ValueError, match="stroke"):
        await use_case.execute(athlete_id=1, stroke=" ", distance=50)
    with pytest.raises(ValueError, match="distance"):
        await use_case.execute(athlete_id=1, stroke="free", distance=0)
