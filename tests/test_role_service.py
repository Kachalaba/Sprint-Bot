from __future__ import annotations

import asyncio
from pathlib import Path

from role_service import ROLE_ATHLETE, ROLE_TRAINER, RoleService


def test_trainer_access_requires_assignment(tmp_path: Path) -> None:
    async def scenario() -> None:
        db_path = tmp_path / "roles.db"
        service = RoleService(db_path)
        await service.init()

        athlete_id = 100
        assigned_trainer = 200
        outsider_trainer = 300

        await service.set_role(athlete_id, ROLE_ATHLETE)
        await service.set_role(assigned_trainer, ROLE_TRAINER)
        await service.set_role(outsider_trainer, ROLE_TRAINER)
        await service.set_trainer(athlete_id, assigned_trainer)

        assert await service.can_access_athlete(athlete_id, athlete_id)
        assert await service.can_access_athlete(assigned_trainer, athlete_id)
        assert not await service.can_access_athlete(
            outsider_trainer,
            athlete_id,
        )

    asyncio.run(scenario())


def test_get_accessible_athletes_for_trainer(tmp_path: Path) -> None:
    async def scenario() -> None:
        db_path = tmp_path / "roles.db"
        service = RoleService(db_path)
        await service.init()

        athlete_one = 100
        athlete_two = 101
        assigned_trainer = 200
        other_trainer = 201
        unassigned_trainer = 202

        for athlete_id in (athlete_one, athlete_two):
            await service.set_role(athlete_id, ROLE_ATHLETE)

        for trainer_id in (assigned_trainer, other_trainer, unassigned_trainer):
            await service.set_role(trainer_id, ROLE_TRAINER)

        await service.set_trainer(athlete_one, assigned_trainer)
        await service.set_trainer(athlete_two, other_trainer)

        assert await service.get_accessible_athletes(assigned_trainer) == (athlete_one,)
        assert await service.get_accessible_athletes(other_trainer) == (athlete_two,)
        assert await service.get_accessible_athletes(unassigned_trainer) == ()

    asyncio.run(scenario())
