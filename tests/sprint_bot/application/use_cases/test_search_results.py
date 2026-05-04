from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from sprint_bot.application.use_cases import (
    SearchFiltersInput,
    SearchPageView,
    SearchResultsUseCase,
)


@dataclass
class _Row:
    result_id: int
    athlete_id: int
    athlete_name: str
    stroke: str
    distance: int
    total_seconds: float
    timestamp: datetime
    is_pr: bool


@dataclass
class _Page:
    rows: tuple[_Row, ...]
    total: int
    page: int
    page_size: int


@pytest.mark.asyncio
async def test_returns_mapped_view() -> None:
    page = _Page(
        rows=(
            _Row(
                1, 7, "Olha", "free", 100, 60.5, datetime(2024, 5, 1), True
            ),
        ),
        total=1,
        page=1,
        page_size=10,
    )
    provider = AsyncMock()
    provider.search_results = AsyncMock(return_value=page)

    use_case = SearchResultsUseCase(provider=provider)
    view = await use_case.execute(
        SearchFiltersInput(athlete_ids=(7,)), page=1, page_size=10
    )

    assert isinstance(view, SearchPageView)
    assert view.total == 1
    assert len(view.rows) == 1
    assert view.rows[0].athlete_name == "Olha"
    assert view.has_next is False


@pytest.mark.asyncio
async def test_uses_filters_factory_when_provided() -> None:
    captured: dict = {}

    def filter_factory(**kwargs):
        captured.update(kwargs)
        return "FILTER"

    provider = AsyncMock()
    provider.search_results = AsyncMock(
        return_value=_Page(rows=(), total=0, page=1, page_size=20)
    )

    use_case = SearchResultsUseCase(
        provider=provider, filters_factory=filter_factory
    )
    await use_case.execute(SearchFiltersInput(strokes=("freestyle",)))

    provider.search_results.assert_awaited_once()
    args, _ = provider.search_results.call_args
    assert args[0] == "FILTER"
    assert captured["strokes"] == ("freestyle",)


@pytest.mark.asyncio
async def test_validates_pagination() -> None:
    use_case = SearchResultsUseCase(provider=AsyncMock())
    with pytest.raises(ValueError, match="page"):
        await use_case.execute(SearchFiltersInput(), page=0)
    with pytest.raises(ValueError, match="page_size"):
        await use_case.execute(SearchFiltersInput(), page=1, page_size=0)
    with pytest.raises(ValueError, match="page_size"):
        await use_case.execute(SearchFiltersInput(), page=1, page_size=999)
