from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from sprint_bot.application.use_cases import ManageRolesUseCase


@pytest.mark.asyncio
async def test_assign_role_normalises_and_persists() -> None:
    roles = AsyncMock()
    roles.set_role = AsyncMock()

    use_case = ManageRolesUseCase(roles=roles)
    assignment = await use_case.assign_role(7, " Trainer ")

    roles.set_role.assert_awaited_once_with(7, "trainer")
    assert assignment.role == "trainer"
    assert assignment.user_id == 7


@pytest.mark.asyncio
async def test_assign_role_rejects_invalid_role() -> None:
    use_case = ManageRolesUseCase(roles=AsyncMock())
    with pytest.raises(ValueError, match="role"):
        await use_case.assign_role(7, "wizard")


@pytest.mark.asyncio
async def test_assign_role_rejects_negative_id() -> None:
    use_case = ManageRolesUseCase(roles=AsyncMock())
    with pytest.raises(ValueError, match="user_id"):
        await use_case.assign_role(0, "athlete")


@pytest.mark.asyncio
async def test_get_role_returns_assignment() -> None:
    roles = AsyncMock()
    roles.get_role = AsyncMock(return_value="athlete")

    use_case = ManageRolesUseCase(roles=roles)
    assignment = await use_case.get_role(11)

    assert assignment.role == "athlete"


@pytest.mark.asyncio
async def test_link_trainer_validates_distinct_ids() -> None:
    roles = AsyncMock()
    use_case = ManageRolesUseCase(roles=roles)

    await use_case.link_trainer(athlete_id=1, trainer_id=2)
    roles.set_trainer.assert_awaited_once_with(athlete_id=1, trainer_id=2)

    with pytest.raises(ValueError, match="different"):
        await use_case.link_trainer(athlete_id=5, trainer_id=5)


@pytest.mark.asyncio
async def test_list_assigned_athletes() -> None:
    roles = AsyncMock()
    roles.athletes_for_trainer = AsyncMock(return_value=[1, 2, 3])

    use_case = ManageRolesUseCase(roles=roles)
    result = await use_case.list_assigned_athletes(trainer_id=42)

    assert result == (1, 2, 3)


@pytest.mark.asyncio
async def test_list_trainers_of() -> None:
    roles = AsyncMock()
    roles.trainers_for_athlete = AsyncMock(return_value=[100])

    use_case = ManageRolesUseCase(roles=roles)
    result = await use_case.list_trainers_of(athlete_id=1)

    assert result == (100,)
