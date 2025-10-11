"""SQLAlchemy-based repository implementations for Postgres."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sprint_bot.application.ports.repositories import AthletesRepo, CoachesRepo, RecordsRepo, ResultsRepo
from sprint_bot.domain.models import Athlete, Coach, Race, SegmentPR, SoB, Split

from .models import AthleteRecord, CoachRecord, RaceRecord, RaceSplitRecord, SegmentPRRecord, SoBRecord


def _seconds_to_timedelta(value: float | None) -> Optional[timedelta]:
    if value is None:
        return None
    return timedelta(seconds=float(value))


def _timedelta_to_seconds(value: timedelta | None) -> float | None:
    return value.total_seconds() if value is not None else None


def _recorded_at(value: datetime | None) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _ensure_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class PostgresAthletesRepo(AthletesRepo):
    """Athlete repository backed by Postgres."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, athlete_id: str) -> Optional[Athlete]:
        async with self._session_factory() as session:
            record = await session.get(AthleteRecord, athlete_id)
            return _athlete_from_record(record) if record else None

    async def get_by_telegram(self, telegram_id: int) -> Optional[Athlete]:
        stmt = select(AthleteRecord).where(AthleteRecord.telegram_id == telegram_id)
        async with self._session_factory() as session:
            record = (await session.scalars(stmt)).first()
            return _athlete_from_record(record) if record else None

    async def list_active(self) -> Sequence[Athlete]:
        stmt = select(AthleteRecord).where(AthleteRecord.is_active.is_(True)).order_by(AthleteRecord.full_name)
        async with self._session_factory() as session:
            result = await session.scalars(stmt)
            return tuple(_athlete_from_record(row) for row in result)

    async def list_by_coach(self, coach_id: str) -> Sequence[Athlete]:
        stmt = (
            select(AthleteRecord)
            .where(AthleteRecord.coach_id == coach_id)
            .order_by(AthleteRecord.full_name)
        )
        async with self._session_factory() as session:
            result = await session.scalars(stmt)
            return tuple(_athlete_from_record(row) for row in result)

    async def upsert(self, athlete: Athlete) -> Athlete:
        async with self._session_factory() as session:
            async with session.begin():
                record = _athlete_to_record(athlete)
                await session.merge(record)
        return athlete


class PostgresCoachesRepo(CoachesRepo):
    """Coach repository backed by Postgres."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, coach_id: str) -> Optional[Coach]:
        async with self._session_factory() as session:
            record = await session.get(CoachRecord, coach_id)
            return _coach_from_record(record) if record else None

    async def get_by_telegram(self, telegram_id: int) -> Optional[Coach]:
        stmt = select(CoachRecord).where(CoachRecord.telegram_id == telegram_id)
        async with self._session_factory() as session:
            record = (await session.scalars(stmt)).first()
            return _coach_from_record(record) if record else None

    async def list_active(self) -> Sequence[Coach]:
        stmt = select(CoachRecord).where(CoachRecord.is_active.is_(True)).order_by(CoachRecord.full_name)
        async with self._session_factory() as session:
            result = await session.scalars(stmt)
            return tuple(_coach_from_record(row) for row in result)

    async def upsert(self, coach: Coach) -> Coach:
        async with self._session_factory() as session:
            async with session.begin():
                record = _coach_to_record(coach)
                await session.merge(record)
        return coach


class PostgresResultsRepo(ResultsRepo):
    """Race results repository backed by Postgres."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, race_id: str) -> Optional[Race]:
        async with self._session_factory() as session:
            record = await session.get(RaceRecord, race_id, options=[selectinload(RaceRecord.splits)])
            return _race_from_record(record) if record else None

    async def list_by_athlete(self, athlete_id: str) -> Sequence[Race]:
        stmt = (
            select(RaceRecord)
            .where(RaceRecord.athlete_id == athlete_id)
            .options(selectinload(RaceRecord.splits))
            .order_by(RaceRecord.event_date.desc())
        )
        async with self._session_factory() as session:
            result = await session.scalars(stmt)
            return tuple(_race_from_record(row) for row in result)

    async def list_recent(self, limit: int = 20) -> Sequence[Race]:
        stmt = select(RaceRecord).options(selectinload(RaceRecord.splits)).order_by(
            RaceRecord.event_date.desc()
        )
        if limit:
            stmt = stmt.limit(limit)
        async with self._session_factory() as session:
            result = await session.scalars(stmt)
            return tuple(_race_from_record(row) for row in result)

    async def save(self, race: Race) -> Race:
        async with self._session_factory() as session:
            async with session.begin():
                record = await session.get(RaceRecord, race.id, options=[selectinload(RaceRecord.splits)])
                if record is None:
                    record = RaceRecord(id=race.id, athlete_id=race.athlete_id)
                record.name = race.name
                record.athlete_id = race.athlete_id
                record.coach_id = race.coach_id
                record.event_date = race.event_date
                record.location = race.location
                record.distance_meters = float(race.distance_meters)
                record.official_time_seconds = _timedelta_to_seconds(race.official_time)
                record.placement_overall = race.placement_overall
                record.placement_age_group = race.placement_age_group

                session.add(record)
                await session.flush()

                await session.execute(delete(RaceSplitRecord).where(RaceSplitRecord.race_id == race.id))
                session.add_all([
                    _split_to_record(race.id, split) for split in race.splits
                ])
        return race


class PostgresRecordsRepo(RecordsRepo):
    """Personal record repository backed by Postgres."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_segment_prs(self, athlete_id: str) -> Sequence[SegmentPR]:
        stmt = select(SegmentPRRecord).where(SegmentPRRecord.athlete_id == athlete_id)
        async with self._session_factory() as session:
            result = await session.scalars(stmt)
            return tuple(_segment_pr_from_record(row) for row in result)

    async def upsert_segment_pr(self, record: SegmentPR) -> SegmentPR:
        async with self._session_factory() as session:
            async with session.begin():
                db_record = _segment_pr_to_record(record)
                await session.merge(db_record)
        return record

    async def get_sob(self, athlete_id: str) -> Optional[SoB]:
        async with self._session_factory() as session:
            sob_record = await session.get(SoBRecord, athlete_id)
            if sob_record is None:
                return None
            segments = await self.list_segment_prs(athlete_id)
            return SoB(
                athlete_id=athlete_id,
                total_time=_seconds_to_timedelta(sob_record.total_time_seconds) or timedelta(0),
                segments=segments,
                generated_at=_ensure_tz(sob_record.generated_at),
            )

    async def save_sob(self, sob: SoB) -> SoB:
        async with self._session_factory() as session:
            async with session.begin():
                sob_record = SoBRecord(
                    athlete_id=sob.athlete_id,
                    total_time_seconds=_timedelta_to_seconds(sob.total_time) or 0.0,
                    generated_at=_ensure_tz(sob.generated_at),
                )
                await session.merge(sob_record)
        return sob


def _athlete_from_record(record: AthleteRecord) -> Athlete:
    return Athlete(
        id=record.id,
        full_name=record.full_name,
        telegram_id=record.telegram_id,
        team_id=record.team_id,
        coach_id=record.coach_id,
        date_of_birth=record.date_of_birth,
        email=record.email,
        is_active=record.is_active,
        pr_5k_seconds=record.pr_5k_seconds,
        pr_10k_seconds=record.pr_10k_seconds,
        notes=record.notes,
    )


def _athlete_to_record(entity: Athlete) -> AthleteRecord:
    return AthleteRecord(
        id=entity.id,
        full_name=entity.full_name,
        telegram_id=entity.telegram_id,
        team_id=entity.team_id,
        coach_id=entity.coach_id,
        date_of_birth=entity.date_of_birth,
        email=entity.email,
        is_active=entity.is_active,
        pr_5k_seconds=entity.pr_5k_seconds,
        pr_10k_seconds=entity.pr_10k_seconds,
        notes=entity.notes,
    )


def _coach_from_record(record: CoachRecord) -> Coach:
    return Coach(
        id=record.id,
        full_name=record.full_name,
        telegram_id=record.telegram_id,
        email=record.email,
        phone=record.phone,
        is_active=record.is_active,
    )


def _coach_to_record(entity: Coach) -> CoachRecord:
    return CoachRecord(
        id=entity.id,
        full_name=entity.full_name,
        telegram_id=entity.telegram_id,
        email=entity.email,
        phone=entity.phone,
        is_active=entity.is_active,
    )


def _race_from_record(record: RaceRecord | None) -> Optional[Race]:
    if record is None:
        return None
    splits = tuple(_split_from_record(row) for row in sorted(record.splits, key=lambda s: s.order))
    return Race(
        id=record.id,
        athlete_id=record.athlete_id,
        name=record.name,
        event_date=record.event_date,
        location=record.location,
        distance_meters=record.distance_meters,
        splits=splits,
        coach_id=record.coach_id,
        official_time=_seconds_to_timedelta(record.official_time_seconds),
        placement_overall=record.placement_overall,
        placement_age_group=record.placement_age_group,
    )


def _split_from_record(record: RaceSplitRecord) -> Split:
    return Split(
        segment_id=record.segment_id,
        order=record.order,
        distance_meters=record.distance_meters,
        elapsed=_seconds_to_timedelta(record.elapsed_seconds) or timedelta(0),
        recorded_at=_recorded_at(record.recorded_at),
        heart_rate=record.heart_rate,
        cadence=record.cadence,
    )


def _split_to_record(race_id: str, split: Split) -> RaceSplitRecord:
    return RaceSplitRecord(
        race_id=race_id,
        segment_id=split.segment_id,
        order=split.order,
        distance_meters=split.distance_meters,
        elapsed_seconds=_timedelta_to_seconds(split.elapsed) or 0.0,
        recorded_at=_ensure_tz(split.recorded_at) if split.recorded_at else None,
        heart_rate=split.heart_rate,
        cadence=split.cadence,
    )


def _segment_pr_from_record(record: SegmentPRRecord) -> SegmentPR:
    return SegmentPR(
        athlete_id=record.athlete_id,
        segment_id=record.segment_id,
        best_time=_seconds_to_timedelta(record.best_time_seconds) or timedelta(0),
        achieved_at=_ensure_tz(record.achieved_at),
        race_id=record.race_id,
    )


def _segment_pr_to_record(record: SegmentPR) -> SegmentPRRecord:
    return SegmentPRRecord(
        athlete_id=record.athlete_id,
        segment_id=record.segment_id,
        best_time_seconds=_timedelta_to_seconds(record.best_time) or 0.0,
        achieved_at=_ensure_tz(record.achieved_at),
        race_id=record.race_id,
    )
