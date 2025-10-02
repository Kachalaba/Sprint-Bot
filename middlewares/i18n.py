"""Middleware for selecting user language and populating context."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from i18n import reset_context_language, set_context_language
from services.user_service import UserService

Handler = Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]]


class I18nMiddleware(BaseMiddleware):
    """Ensure handlers operate with the language stored in user profile."""

    def __init__(
        self,
        user_service: UserService,
        *,
        default_language: str = "uk",
        context_key: str = "lang",
    ) -> None:
        self._user_service = user_service
        self._default_language = default_language
        self._context_key = context_key

    async def __call__(
        self, handler: Handler, event: TelegramObject, data: Dict[str, Any]
    ) -> Any:
        lang = await self._resolve_language(event, data)
        data[self._context_key] = lang

        event_ctx = getattr(event, "ctx", None)
        if event_ctx is not None:
            try:
                event_ctx[self._context_key] = lang
            except (TypeError, AttributeError):  # pragma: no cover - defensive
                pass

        token = set_context_language(lang)
        try:
            return await handler(event, data)
        finally:
            reset_context_language(token)

    async def _resolve_language(
        self, event: TelegramObject, data: Dict[str, Any]
    ) -> str:
        lang = data.get(self._context_key)
        if isinstance(lang, str) and lang:
            return lang

        user = getattr(event, "from_user", None)
        if user is None:
            return self._default_language

        profile = await self._user_service.get_profile(user.id)
        if profile and getattr(profile, "language", None):
            return profile.language

        return self._default_language
