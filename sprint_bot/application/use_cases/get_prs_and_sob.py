"""GetPRsAndSOB use case: build personal-best comparison snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SegmentComparisonView:
    """Per-segment comparison between current and previous best splits."""

    index: int
    current_seconds: float
    previous_best_seconds: float | None
    improved: bool


@dataclass(frozen=True, slots=True)
class ComparisonView:
    """Aggregate of total/segment PRs and Sum-of-Best status."""

    total_previous_seconds: float | None
    total_current_seconds: float
    total_improved: bool
    segments: tuple[SegmentComparisonView, ...]
    sob_total_seconds: float | None
    sob_segment_count: int


class PRComparisonProvider(Protocol):
    """Subset of the PB service required by the use case."""

    async def compare_last_with_pb(
        self, athlete_id: int, stroke: str, distance: int
    ) -> object:
        """Return a comparison summary or ``None`` when no data exists."""


class GetPRsAndSOBUseCase:
    """Wrap the PB service with input validation and DTO mapping."""

    def __init__(self, *, pb: PRComparisonProvider) -> None:
        self._pb = pb

    async def execute(
        self, *, athlete_id: int, stroke: str, distance: int
    ) -> ComparisonView | None:
        if athlete_id <= 0:
            raise ValueError("athlete_id must be positive")
        if not stroke.strip():
            raise ValueError("stroke is required")
        if distance <= 0:
            raise ValueError("distance must be positive")
        summary = await self._pb.compare_last_with_pb(athlete_id, stroke, distance)
        if summary is None:
            return None
        return self._to_view(summary)

    @staticmethod
    def _to_view(summary: object) -> ComparisonView:
        sob = getattr(summary, "sob", None)
        segments = tuple(
            SegmentComparisonView(
                index=int(getattr(item, "index", 0)),
                current_seconds=float(getattr(item, "current", 0.0)),
                previous_best_seconds=(
                    float(getattr(item, "previous_best"))
                    if getattr(item, "previous_best", None) is not None
                    else None
                ),
                improved=bool(getattr(item, "improved", False)),
            )
            for item in (getattr(summary, "segments", ()) or ())
        )
        sob_segments = tuple(getattr(sob, "segments", ()) or ())
        return ComparisonView(
            total_previous_seconds=getattr(summary, "total_previous", None),
            total_current_seconds=float(getattr(summary, "total_current", 0.0)),
            total_improved=bool(getattr(summary, "total_improved", False)),
            segments=segments,
            sob_total_seconds=getattr(sob, "total", None),
            sob_segment_count=len(sob_segments),
        )


__all__ = [
    "ComparisonView",
    "GetPRsAndSOBUseCase",
    "PRComparisonProvider",
    "SegmentComparisonView",
]
