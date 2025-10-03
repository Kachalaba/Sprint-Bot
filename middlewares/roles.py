"""Middleware for injecting user role into handler context."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from role_service import RoleService
from utils.roles import DEFAULT_ROLE_KEY, localize_role

Handler = Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]]


class RoleMiddleware(BaseMiddleware):
    """Populate handler data with the current user's role."""

    def __init__(
        self, role_service: RoleService, *, context_key: str = DEFAULT_ROLE_KEY
    ) -> None:
        self._role_service = role_service
        self._context_key = context_key

    async def __call__(
        self, handler: Handler, event: TelegramObject, data: Dict[str, Any]
    ) -> Any:
        if self._context_key in data:
            return await handler(event, data)

        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        role = await self._role_service.get_role(user.id)
        data[self._context_key] = role
        data[f"{self._context_key}_label"] = localize_role(role)
        return await handler(event, data)
