"""Filters for enforcing role-based access control."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Set

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from role_service import RoleService


class RoleFilter(BaseFilter):
    """Allow handling updates only for users with the required role."""

    def __init__(self, *roles: str) -> None:
        if not roles:
            raise ValueError("RoleFilter requires at least one role")
        self.allowed_roles: Set[str] = set(roles)

    async def __call__(self, event: TelegramObject, data: Dict[str, Any]) -> bool:
        role_service: RoleService | None = data.get("role_service")
        if role_service is None:
            return False

        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
        else:  # pragma: no cover - defensive branch for unsupported events
            user = getattr(event, "from_user", None)
            if user is not None:
                user_id = user.id
        if user_id is None:
            return False
        role = await role_service.get_role(user_id)
        return role in self.allowed_roles

    def extend(self, roles: Iterable[str]) -> "RoleFilter":
        """Return new filter that also allows provided roles."""

        new_filter = RoleFilter(*self.allowed_roles)
        new_filter.allowed_roles.update(roles)
        return new_filter
