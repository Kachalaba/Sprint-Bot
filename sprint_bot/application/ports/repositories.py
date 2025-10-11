"""Repository contracts for accessing persistent data."""

from __future__ import annotations

from typing import Optional, Protocol, Sequence

from sprint_bot.domain.models import Athlete, Coach, Race, SegmentPR, SoB


class AthleteRepository(Protocol):
    """Provides access to athlete profiles."""

    async def get(self, athlete_id: str) -> Optional[Athlete]:
        """Fetch an athlete by identifier."""

    async def get_by_telegram(self, telegram_id: int) -> Optional[Athlete]:
        """Lookup athlete by Telegram user id."""

    async def list_active(self) -> Sequence[Athlete]:
        """Return active athletes for operational flows."""

    async def list_by_coach(self, coach_id: str) -> Sequence[Athlete]:
        """Return athletes assigned to a specific coach."""

    async def upsert(self, athlete: Athlete) -> Athlete:
        """Create or update an athlete record."""


class CoachRepository(Protocol):
    """Provides access to coaching staff profiles."""

    async def get(self, coach_id: str) -> Optional[Coach]:
        """Fetch coach by identifier."""

    async def get_by_telegram(self, telegram_id: int) -> Optional[Coach]:
        """Lookup coach by Telegram id."""

    async def list_active(self) -> Sequence[Coach]:
        """Return all active coaches."""

    async def upsert(self, coach: Coach) -> Coach:
        """Persist the coach entity."""


class RaceRepository(Protocol):
    """Persists races with nested split data."""

    async def get(self, race_id: str) -> Optional[Race]:
        """Fetch a race aggregate."""

    async def list_by_athlete(self, athlete_id: str) -> Sequence[Race]:
        """Return races for a given athlete."""

    async def list_recent(self, limit: int = 20) -> Sequence[Race]:
        """Return the most recent races across roster."""

    async def save(self, race: Race) -> Race:
        """Persist race and underlying splits atomically."""


class PerformanceRepository(Protocol):
    """Handles personal records and sum-of-bests aggregations."""

    async def list_segment_prs(self, athlete_id: str) -> Sequence[SegmentPR]:
        """Return segment bests for athlete."""

    async def upsert_segment_pr(self, record: SegmentPR) -> SegmentPR:
        """Persist updated segment personal record."""

    async def get_sob(self, athlete_id: str) -> Optional[SoB]:
        """Fetch cached sum-of-bests snapshot."""

    async def save_sob(self, sob: SoB) -> SoB:
        """Persist or refresh sum-of-bests snapshot."""
