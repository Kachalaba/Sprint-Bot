"""ManageRoles use case: assign roles and trainer relationships."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence


_ALLOWED_ROLES: frozenset[str] = frozenset(
    {"athlete", "trainer", "admin", "guest"}
)


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    """User identity + role summary returned to handlers."""

    user_id: int
    role: str


class RoleStore(Protocol):
    """Subset of ``RoleService`` required by the use case."""

    async def set_role(self, user_id: int, role: str) -> None: ...
    async def get_role(self, user_id: int) -> str: ...
    async def set_trainer(self, athlete_id: int, trainer_id: int) -> None: ...
    async def athletes_for_trainer(self, trainer_id: int) -> Sequence[int]: ...
    async def trainers_for_athlete(self, athlete_id: int) -> Sequence[int]: ...


class ManageRolesUseCase:
    """Encapsulate role and trainer assignment business rules."""

    def __init__(self, *, roles: RoleStore) -> None:
        self._roles = roles

    async def assign_role(self, user_id: int, role: str) -> RoleAssignment:
        if user_id <= 0:
            raise ValueError("user_id must be positive")
        normalised = role.strip().lower()
        if normalised not in _ALLOWED_ROLES:
            raise ValueError(
                f"role must be one of {sorted(_ALLOWED_ROLES)}, got '{role}'"
            )
        await self._roles.set_role(user_id, normalised)
        return RoleAssignment(user_id=user_id, role=normalised)

    async def get_role(self, user_id: int) -> RoleAssignment:
        if user_id <= 0:
            raise ValueError("user_id must be positive")
        role = await self._roles.get_role(user_id)
        return RoleAssignment(user_id=user_id, role=role)

    async def link_trainer(self, *, athlete_id: int, trainer_id: int) -> None:
        if athlete_id <= 0 or trainer_id <= 0:
            raise ValueError("athlete_id and trainer_id must be positive")
        if athlete_id == trainer_id:
            raise ValueError("athlete and trainer must be different users")
        await self._roles.set_trainer(athlete_id=athlete_id, trainer_id=trainer_id)

    async def list_assigned_athletes(self, trainer_id: int) -> tuple[int, ...]:
        if trainer_id <= 0:
            raise ValueError("trainer_id must be positive")
        return tuple(await self._roles.athletes_for_trainer(trainer_id))

    async def list_trainers_of(self, athlete_id: int) -> tuple[int, ...]:
        if athlete_id <= 0:
            raise ValueError("athlete_id must be positive")
        return tuple(await self._roles.trainers_for_athlete(athlete_id))


__all__ = [
    "ManageRolesUseCase",
    "RoleAssignment",
    "RoleStore",
]
