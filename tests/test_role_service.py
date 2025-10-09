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
