from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from sprint_bot.application.use_cases import (
    AddResultRequest,
    AddResultResponse,
    AddResultUseCase,
)


def _request(**overrides) -> AddResultRequest:
    base = dict(
        athlete_id=42,
        athlete_name="Vasyl",
        stroke="freestyle",
        distance=100,
        total_seconds=58.4,
        splits=(28.1, 30.3),
        timestamp=datetime(2024, 5, 1, 12, 0, 0),
    )
    base.update(overrides)
    return AddResultRequest(**base)


@pytest.mark.asyncio
async def test_records_valid_request() -> None:
    response = AddResultResponse(
        result_id=1, is_total_pr=True, segment_pr_count=1, sob_total_seconds=58.0
    )
    recorder = AsyncMock()
    recorder.record = AsyncMock(return_value=response)

    use_case = AddResultUseCase(recorder=recorder)
    result = await use_case.execute(_request())

    recorder.record.assert_awaited_once()
    assert result is response


@pytest.mark.asyncio
async def test_rejects_non_positive_athlete_id() -> None:
    use_case = AddResultUseCase(recorder=AsyncMock())
    with pytest.raises(ValueError, match="athlete_id"):
        await use_case.execute(_request(athlete_id=0))


@pytest.mark.asyncio
async def test_rejects_blank_name() -> None:
    use_case = AddResultUseCase(recorder=AsyncMock())
    with pytest.raises(ValueError, match="athlete_name"):
        await use_case.execute(_request(athlete_name="  "))


@pytest.mark.asyncio
async def test_rejects_blank_stroke() -> None:
    use_case = AddResultUseCase(recorder=AsyncMock())
    with pytest.raises(ValueError, match="stroke"):
        await use_case.execute(_request(stroke=""))


@pytest.mark.asyncio
async def test_rejects_zero_distance() -> None:
    use_case = AddResultUseCase(recorder=AsyncMock())
    with pytest.raises(ValueError, match="distance"):
        await use_case.execute(_request(distance=0))


@pytest.mark.asyncio
async def test_rejects_zero_total() -> None:
    use_case = AddResultUseCase(recorder=AsyncMock())
    with pytest.raises(ValueError, match="total_seconds"):
        await use_case.execute(_request(total_seconds=0))


@pytest.mark.asyncio
async def test_rejects_empty_splits() -> None:
    use_case = AddResultUseCase(recorder=AsyncMock())
    with pytest.raises(ValueError, match="splits"):
        await use_case.execute(_request(splits=()))


@pytest.mark.asyncio
async def test_rejects_non_positive_split() -> None:
    use_case = AddResultUseCase(recorder=AsyncMock())
    with pytest.raises(ValueError, match="split"):
        await use_case.execute(_request(splits=(28.0, -1.0)))
