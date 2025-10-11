"""Storage abstraction combining repositories behind a single backend."""

from __future__ import annotations

from typing import Protocol

from .repositories import AthletesRepo, CoachesRepo, RecordsRepo, ResultsRepo


class Storage(Protocol):
    """Provides access to persistence backends grouped under a single facade."""

    @property
    def athletes(self) -> AthletesRepo:
        """Return repository managing athlete entities."""

    @property
    def coaches(self) -> CoachesRepo:
        """Return repository managing coach entities."""

    @property
    def results(self) -> ResultsRepo:
        """Return repository managing race results."""

    @property
    def records(self) -> RecordsRepo:
        """Return repository managing PR/Sum-of-Bests aggregates."""

    async def init(self) -> None:
        """Initialise underlying connections or schemas if needed."""

    async def close(self) -> None:
        """Release any allocated resources (connections, pools, caches)."""
