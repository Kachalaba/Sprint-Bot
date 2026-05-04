"""GetProgress use case: produce weekly highlights for an athlete."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class HighlightView:
    """Single attempt highlighted in the progress report."""

    stroke: str
    distance: int
    total_seconds: float
    timestamp: datetime
    is_pr: bool


@dataclass(frozen=True, slots=True)
class WeeklyProgressView:
    """Athlete-facing snapshot of the last seven days."""

    athlete_id: int
    attempts: int
    pr_count: int
    highlights: tuple[HighlightView, ...]


class StatsProvider(Protocol):
    """Subset of ``StatsService`` consumed by the use case."""

    async def weekly_progress(self, athlete_id: int) -> object:
        """Return the per-week aggregate for the athlete."""


class GetProgressUseCase:
    """Validate the request and translate the stats payload to a view."""

    def __init__(self, *, stats: StatsProvider) -> None:
        self._stats = stats

    async def execute(self, athlete_id: int) -> WeeklyProgressView:
        if athlete_id <= 0:
            raise ValueError("athlete_id must be positive")
        progress = await self._stats.weekly_progress(athlete_id)
        highlights = tuple(
            HighlightView(
                stroke=item.stroke,
                distance=item.distance,
                total_seconds=item.total_seconds,
                timestamp=item.timestamp,
                is_pr=item.is_pr,
            )
            for item in self._iter_highlights(progress)
        )
        return WeeklyProgressView(
            athlete_id=getattr(progress, "athlete_id", athlete_id),
            attempts=getattr(progress, "attempts", 0),
            pr_count=getattr(progress, "pr_count", 0),
            highlights=highlights,
        )

    @staticmethod
    def _iter_highlights(progress: object) -> Sequence[object]:
        return tuple(getattr(progress, "highlights", ()) or ())


__all__ = [
    "GetProgressUseCase",
    "HighlightView",
    "StatsProvider",
    "WeeklyProgressView",
]
