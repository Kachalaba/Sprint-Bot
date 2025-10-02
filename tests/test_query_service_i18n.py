"""Tests for localized responses from query service consumers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from handlers.search import SearchStates, select_pr
from i18n import reset_context_language, set_context_language, t
from keyboards import SearchFilterCB
from services.query_service import SearchPage


class DummyMessage:
    """Simplified message stub capturing bot replies."""

    def __init__(self) -> None:
        self.text = ""
        self.from_user = SimpleNamespace(id=1)
        self.chat = SimpleNamespace(id=1)
        self.answer = AsyncMock()


class DummyCallback:
    """Minimal callback stub for invoking handlers."""

    def __init__(self, message: DummyMessage) -> None:
        self.message = message
        self.from_user = message.from_user
        self.answer = AsyncMock()


def _make_state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


class EmptyQueryService:
    """Query service stub returning no results."""

    async def search_results(self, filters, *, page: int, page_size: int) -> SearchPage:  # type: ignore[override]
        return SearchPage(items=(), total=0, page=1, pages=0)


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_empty_results_message_localized(lang: str) -> None:
    async def scenario() -> None:
        state = _make_state()
        await state.set_state(SearchStates.choose_pr)
        callback = DummyCallback(DummyMessage())
        service = EmptyQueryService()

        await select_pr(
            callback, state, SearchFilterCB(field="pr", value="all"), service
        )

        args, _ = callback.message.answer.await_args
        assert args[0] == t("search.empty")

    token = set_context_language(lang)
    try:
        asyncio.run(scenario())
    finally:
        reset_context_language(token)
