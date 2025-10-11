"""Domain entities shared between use-cases and adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional, Sequence


@dataclass(slots=True, frozen=True)
class Athlete:
    """Represents an athlete tracked by the Sprint Bot."""

    id: str
    full_name: str
    telegram_id: Optional[int]
    team_id: Optional[str]
    coach_id: Optional[str]
    date_of_birth: Optional[date] = None
    email: Optional[str] = None
    is_active: bool = True
    pr_5k_seconds: Optional[float] = None
    pr_10k_seconds: Optional[float] = None
    notes: Optional[str] = None


@dataclass(slots=True, frozen=True)
class Coach:
    """Represents a coach responsible for one or more athletes."""

    id: str
    full_name: str
    telegram_id: Optional[int]
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool = True


@dataclass(slots=True, frozen=True)
class Split:
    """A timed effort for a race segment."""

    segment_id: str
    order: int
    distance_meters: float
    elapsed: timedelta
    recorded_at: Optional[datetime] = None
    heart_rate: Optional[int] = None
    cadence: Optional[int] = None


@dataclass(slots=True, frozen=True)
class Race:
    """Represents a competitive event with split-level telemetry."""

    id: str
    athlete_id: str
    name: str
    event_date: date
    location: Optional[str]
    distance_meters: float
    splits: Sequence[Split] = field(default_factory=tuple)
    coach_id: Optional[str] = None
    official_time: Optional[timedelta] = None
    placement_overall: Optional[int] = None
    placement_age_group: Optional[int] = None


@dataclass(slots=True, frozen=True)
class SegmentPR:
    """Stores a personal record for a specific course segment."""

    athlete_id: str
    segment_id: str
    best_time: timedelta
    achieved_at: datetime
    race_id: Optional[str] = None


@dataclass(slots=True, frozen=True)
class SoB:
    """Sum-of-bests aggregate for benchmarking athlete performance."""

    athlete_id: str
    total_time: timedelta
    segments: Sequence[SegmentPR] = field(default_factory=tuple)
    generated_at: datetime = field(default_factory=datetime.utcnow)
