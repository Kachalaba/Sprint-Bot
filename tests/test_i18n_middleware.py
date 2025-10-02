from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from i18n import get_current_language, t
from middlewares.i18n import I18nMiddleware


class StubUserService:
    def __init__(self, languages: dict[int, str]) -> None:
        self._languages = languages

    async def get_profile(self, telegram_id: int) -> Any | None:
        language = self._languages.get(telegram_id)
        if language is None:
            return None
        return SimpleNamespace(language=language)


def test_user_language_is_used_from_profile() -> None:
    service = StubUserService({1: "ru"})
    middleware = I18nMiddleware(service)
    event = SimpleNamespace(from_user=SimpleNamespace(id=1), ctx={})
    data: dict[str, Any] = {}

    async def scenario() -> tuple[str, str, str]:
        async def handler(evt, ctx):
            return t("menu.add_result"), ctx["lang"], evt.ctx["lang"]

        return await middleware(handler, event, data)

    text, data_lang, ctx_lang = asyncio.run(scenario())
    assert text == "Добавить результат"
    assert data_lang == "ru"
    assert ctx_lang == "ru"
    assert get_current_language() == "uk"


def test_default_language_is_used_when_profile_missing() -> None:
    service = StubUserService({})
    middleware = I18nMiddleware(service)
    event = SimpleNamespace(from_user=SimpleNamespace(id=2), ctx={})
    data: dict[str, Any] = {}

    async def scenario() -> tuple[str, str, str]:
        async def handler(evt, ctx):
            return t("menu.start", name="Анна"), ctx["lang"], evt.ctx["lang"]

        return await middleware(handler, event, data)

    text, data_lang, ctx_lang = asyncio.run(scenario())
    assert text == "Привіт, Анна!"
    assert data_lang == "uk"
    assert ctx_lang == "uk"
    assert get_current_language() == "uk"
