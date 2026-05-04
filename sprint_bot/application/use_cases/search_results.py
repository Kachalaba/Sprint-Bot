"""SearchResults use case: paginate stored attempts with filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class SearchFiltersInput:
    """Filter parameters used to query the result archive."""

    athlete_ids: tuple[int, ...] = ()
    strokes: tuple[str, ...] = ()
    distances: tuple[int, ...] = ()
    date_from: datetime | None = None
    date_to: datetime | None = None
    only_prs: bool = False


@dataclass(frozen=True, slots=True)
class SearchResultRow:
    """Single row in the result archive."""

    result_id: int
    athlete_id: int
    athlete_name: str
    stroke: str
    distance: int
    total_seconds: float
    timestamp: datetime
    is_pr: bool


@dataclass(frozen=True, slots=True)
class SearchPageView:
    """Paginated page of search hits."""

    rows: tuple[SearchResultRow, ...]
    total: int
    page: int
    page_size: int

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total


class SearchResultsProvider(Protocol):
    """Subset of ``QueryService`` consumed by the use case."""

    async def search_results(
        self,
        filters: object,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> object:
        """Return a paginated query result."""


class SearchResultsUseCase:
    """Validate query parameters and translate the storage payload."""

    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    def __init__(
        self,
        *,
        provider: SearchResultsProvider,
        filters_factory: type | None = None,
    ) -> None:
        self._provider = provider
        self._filters_factory = filters_factory

    async def execute(
        self,
        filters: SearchFiltersInput,
        *,
        page: int = 1,
        page_size: int | None = None,
    ) -> SearchPageView:
        if page < 1:
            raise ValueError("page must be >= 1")
        size = self.DEFAULT_PAGE_SIZE if page_size is None else page_size
        if size <= 0 or size > self.MAX_PAGE_SIZE:
            raise ValueError(
                f"page_size must be between 1 and {self.MAX_PAGE_SIZE}"
            )

        provider_filters = self._adapt_filters(filters)
        page_obj = await self._provider.search_results(
            provider_filters, page=page, page_size=size
        )
        rows = tuple(self._row(item) for item in self._iter_rows(page_obj))
        return SearchPageView(
            rows=rows,
            total=int(getattr(page_obj, "total", len(rows))),
            page=int(getattr(page_obj, "page", page)),
            page_size=int(getattr(page_obj, "page_size", size)),
        )

    def _adapt_filters(self, filters: SearchFiltersInput) -> object:
        if self._filters_factory is None:
            return filters
        return self._filters_factory(
            athlete_ids=filters.athlete_ids,
            strokes=filters.strokes,
            distances=filters.distances,
            date_from=filters.date_from,
            date_to=filters.date_to,
            only_prs=filters.only_prs,
        )

    @staticmethod
    def _iter_rows(page_obj: object) -> Sequence[object]:
        return tuple(getattr(page_obj, "rows", ()) or ())

    @staticmethod
    def _row(item: object) -> SearchResultRow:
        return SearchResultRow(
            result_id=int(getattr(item, "result_id", getattr(item, "id", 0))),
            athlete_id=int(getattr(item, "athlete_id", 0)),
            athlete_name=str(getattr(item, "athlete_name", "")),
            stroke=str(getattr(item, "stroke", "")),
            distance=int(getattr(item, "distance", 0)),
            total_seconds=float(getattr(item, "total_seconds", 0.0)),
            timestamp=getattr(item, "timestamp", datetime.utcnow()),
            is_pr=bool(getattr(item, "is_pr", False)),
        )


__all__ = [
    "SearchFiltersInput",
    "SearchPageView",
    "SearchResultRow",
    "SearchResultsProvider",
    "SearchResultsUseCase",
]
