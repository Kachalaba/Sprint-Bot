"""AddResult use case: record a swim attempt with validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AddResultRequest:
    """Inbound payload describing a recorded attempt."""

    athlete_id: int
    athlete_name: str
    stroke: str
    distance: int
    total_seconds: float
    splits: tuple[float, ...]
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class AddResultResponse:
    """Outcome after persisting an attempt."""

    result_id: int
    is_total_pr: bool
    segment_pr_count: int
    sob_total_seconds: float | None


class ResultsRecorder(Protocol):
    """Persistence contract for storing a recorded attempt."""

    async def record(self, request: "AddResultRequest") -> AddResultResponse:
        """Persist the attempt and return analysis hints."""


class AddResultUseCase:
    """Validate and persist a result through a ``ResultsRecorder``."""

    def __init__(self, *, recorder: ResultsRecorder) -> None:
        self._recorder = recorder

    async def execute(self, request: AddResultRequest) -> AddResultResponse:
        self._validate(request)
        return await self._recorder.record(request)

    @staticmethod
    def _validate(request: AddResultRequest) -> None:
        if request.athlete_id <= 0:
            raise ValueError("athlete_id must be positive")
        if not request.athlete_name.strip():
            raise ValueError("athlete_name is required")
        if not request.stroke.strip():
            raise ValueError("stroke is required")
        if request.distance <= 0:
            raise ValueError("distance must be positive")
        if request.total_seconds <= 0:
            raise ValueError("total_seconds must be positive")
        if not request.splits:
            raise ValueError("splits must contain at least one segment")
        if any(split <= 0 for split in request.splits):
            raise ValueError("each split must be positive")


__all__ = [
    "AddResultRequest",
    "AddResultResponse",
    "AddResultUseCase",
    "ResultsRecorder",
]
