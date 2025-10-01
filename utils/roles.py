"""Role-based access helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Set

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from role_service import RoleService

DEFAULT_ROLE_KEY = "user_role"


class RequireRolesFilter(BaseFilter):
    """Filter allowing events only for specific roles."""

    def __init__(self, *roles: str, context_key: str = DEFAULT_ROLE_KEY) -> None:
        if not roles:
            raise ValueError("require_roles() expects at least one role")
        self.allowed_roles: Set[str] = set(roles)
        self.context_key = context_key

    async def __call__(self, event: TelegramObject, data: Dict[str, Any]) -> bool:
        role = data.get(self.context_key)
        if role is None:
            role_service: RoleService | None = data.get("role_service")
            user = getattr(event, "from_user", None)
            if role_service is None or user is None:
                return False
            role = await role_service.get_role(user.id)
            data[self.context_key] = role
        return str(role) in self.allowed_roles

    def extend(self, roles: Iterable[str]) -> "RequireRolesFilter":
        """Return new filter instance with additional roles allowed."""

        return RequireRolesFilter(*self.allowed_roles.union(set(roles)), context_key=self.context_key)


def require_roles(*roles: str, context_key: str = DEFAULT_ROLE_KEY) -> RequireRolesFilter:
    """Shortcut returning :class:`RequireRolesFilter` instance."""

    return RequireRolesFilter(*roles, context_key=context_key)
