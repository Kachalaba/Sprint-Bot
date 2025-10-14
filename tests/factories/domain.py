"""Domain factories for Sprint Bot tests."""

from __future__ import annotations

import datetime as dt
from typing import Iterable, Sequence

import factory

from sprint_bot.domain.models import Athlete, Race, Split


class AthleteFactory(factory.Factory):
    """Factory building :class:`~sprint_bot.domain.models.Athlete` entities."""

    id = factory.Sequence(lambda n: f"athlete-{n:04d}")
    full_name = factory.Faker("name")
    telegram_id = factory.Sequence(lambda n: 10_000 + n)
    team_id = factory.Sequence(lambda n: f"team-{n:03d}")
    coach_id = factory.Sequence(lambda n: f"coach-{n:03d}")
    date_of_birth = factory.LazyFunction(lambda: dt.date(1995, 1, 1))
    email = factory.LazyAttribute(lambda obj: f"{obj.id}@example.com")
    is_active = True
    pr_5k_seconds = 1100.5
    pr_10k_seconds = 2400.7
    notes = factory.Faker("sentence")

    class Meta:
        model = Athlete
        abstract = False


class SplitFactory(factory.Factory):
    """Factory constructing :class:`~sprint_bot.domain.models.Split` values."""

    segment_id = factory.Sequence(lambda n: f"segment-{n:02d}")
    order = factory.Sequence(lambda n: n + 1)
    distance_meters = 100.0
    elapsed = factory.LazyAttribute(lambda _: dt.timedelta(seconds=75))
    recorded_at = factory.LazyFunction(
        lambda: dt.datetime.utcnow().replace(microsecond=0)
    )
    heart_rate = factory.Sequence(lambda n: 150 + (n % 10))
    cadence = factory.Sequence(lambda n: 80 + (n % 5))

    class Meta:
        model = Split
        abstract = False


class RaceFactory(factory.Factory):
    """Factory generating :class:`~sprint_bot.domain.models.Race` aggregates."""

    id = factory.Sequence(lambda n: f"race-{n:04d}")
    athlete_id = factory.Sequence(lambda n: f"athlete-{n:04d}")
    name = factory.Faker("city")
    event_date = factory.LazyFunction(lambda: dt.date.today())
    location = factory.Faker("city")
    distance_meters = 5_000.0
    coach_id = factory.Sequence(lambda n: f"coach-{n:03d}")
    official_time = factory.LazyAttribute(lambda _: dt.timedelta(minutes=20))
    placement_overall = factory.Sequence(lambda n: n + 1)
    placement_age_group = factory.Sequence(lambda n: (n % 10) + 1)

    class Meta:
        model = Race
        abstract = False

    @factory.post_generation
    def splits(
        self, create: bool, extracted: Sequence[Split] | None, **unused: object
    ) -> None:
        """Attach generated or provided splits to immutable dataclass."""

        if extracted:
            value: Iterable[Split] = extracted
        else:
            value = SplitFactory.build_batch(3)
        object.__setattr__(self, "splits", tuple(value))
