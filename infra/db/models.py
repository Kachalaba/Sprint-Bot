"""Declarative models for Sprint Bot persistence."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    type_annotation_map = {
        date: Date(),
        datetime: DateTime(timezone=True),
    }


class AthleteRecord(Base):
    """Persistent representation of an athlete."""

    __tablename__ = "athletes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255))
    telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    team_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    coach_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("coaches.id"), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pr_5k_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    pr_10k_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    races: Mapped[list["RaceRecord"]] = relationship(back_populates="athlete")


class CoachRecord(Base):
    """Persistent representation of a coach."""

    __tablename__ = "coaches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255))
    telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    athletes: Mapped[list[AthleteRecord]] = relationship(back_populates="coach")


AthleteRecord.coach = relationship(CoachRecord, back_populates="athletes", lazy="joined")  # type: ignore[attr-defined]


class RaceRecord(Base):
    """Race aggregate storing metadata and telemetry link."""

    __tablename__ = "races"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    athlete_id: Mapped[str] = mapped_column(String(64), ForeignKey("athletes.id"), nullable=False)
    coach_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("coaches.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    distance_meters: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    official_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    placement_overall: Mapped[int | None] = mapped_column(Integer, nullable=True)
    placement_age_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    athlete: Mapped[AthleteRecord] = relationship(back_populates="races")
    splits: Mapped[list["RaceSplitRecord"]] = relationship(
        back_populates="race", cascade="all, delete-orphan", order_by="RaceSplitRecord.order"
    )


class RaceSplitRecord(Base):
    """Individual race segment split."""

    __tablename__ = "race_splits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[str] = mapped_column(String(64), ForeignKey("races.id", ondelete="CASCADE"), nullable=False)
    segment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_meters: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    elapsed_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cadence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    race: Mapped[RaceRecord] = relationship(back_populates="splits")


class SegmentPRRecord(Base):
    """Segment personal record for an athlete."""

    __tablename__ = "segment_prs"

    athlete_id: Mapped[str] = mapped_column(String(64), ForeignKey("athletes.id", ondelete="CASCADE"), primary_key=True)
    segment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    best_time_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    achieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    race_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("races.id"), nullable=True)


class SoBRecord(Base):
    """Sum-of-bests aggregate for an athlete."""

    __tablename__ = "sum_of_bests"

    athlete_id: Mapped[str] = mapped_column(String(64), ForeignKey("athletes.id", ondelete="CASCADE"), primary_key=True)
    total_time_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
