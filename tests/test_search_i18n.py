import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Dict
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from handlers.search import (
    input_dates,
    paginate,
    select_athlete,
    select_distance,
    select_pr,
    select_style,
    start_search,
)
from i18n import reset_context_language, set_context_language, t
from keyboards import SearchFilterCB, SearchPageCB
from services.query_service import SearchPage, SearchResult


class DummyMessage:
    def __init__(self, text: str = "", user_id: int = 42, chat_id: int = 24) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(id=chat_id)
        self.answer = AsyncMock()
        self.edit_text = AsyncMock()


class DummyCallback:
    def __init__(self, message: DummyMessage) -> None:
        self.message = message
        self.from_user = message.from_user
        self.data = ""
        self.answer = AsyncMock()


def _make_state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=24, user_id=42)
    return FSMContext(storage=storage, key=key)


class FakeRoleService:
    async def get_accessible_athletes(self, requester_id: int) -> tuple[int, ...]:
        return (1,)

    async def list_users(self, roles=None):  # type: ignore[override]
        return (SimpleNamespace(telegram_id=1, full_name="User One"),)


class FakeQueryService:
    def __init__(self, pages: Dict[int, SearchPage]) -> None:
        self._pages = pages

    async def search_results(self, filters, *, page: int, page_size: int) -> SearchPage:  # type: ignore[override]
        return self._pages[page]


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_search_i18n_filters_and_pagination(lang: str) -> None:
    async def scenario() -> None:
        state = _make_state()
        role_service = FakeRoleService()
        base_time = datetime(2024, 1, 1, 10, 0)
        page_one_items = tuple(
            SearchResult(
                result_id=idx,
                athlete_id=1,
                athlete_name="User One",
                stroke="freestyle",
                distance=100,
                total_seconds=70.0 + idx,
                timestamp=base_time + timedelta(days=idx),
                is_pr=idx == 1,
            )
            for idx in range(1, 6)
        )
        page_two_items = (
            SearchResult(
                result_id=6,
                athlete_id=1,
                athlete_name="User One",
                stroke="freestyle",
                distance=100,
                total_seconds=80.0,
                timestamp=base_time + timedelta(days=6),
                is_pr=False,
            ),
        )
        pages = {
            1: SearchPage(items=page_one_items, total=6, page=1, pages=2),
            2: SearchPage(items=page_two_items, total=6, page=2, pages=2),
        }
        query_service = FakeQueryService(pages)

        start_msg = DummyMessage(text="/search")
        await start_search(start_msg, state, role_service)

        athlete_cb = DummyCallback(DummyMessage())
        await select_athlete(
            athlete_cb, state, SearchFilterCB(field="athlete", value="1")
        )

        style_cb = DummyCallback(DummyMessage())
        await select_style(
            style_cb, state, SearchFilterCB(field="stroke", value="freestyle")
        )

        distance_cb = DummyCallback(DummyMessage())
        await select_distance(
            distance_cb, state, SearchFilterCB(field="distance", value="100")
        )

        await input_dates(DummyMessage("2024-01-01 2024-02-01"), state)

        pr_msg = DummyMessage()
        pr_cb = DummyCallback(pr_msg)
        await select_pr(
            pr_cb, state, SearchFilterCB(field="pr", value="only"), query_service
        )

        args, kwargs = pr_msg.answer.await_args
        message_text = args[0]
        markup = kwargs["reply_markup"]

        expected_entries = [
            t("search.filter.user", value="User One"),
            t("search.filter.style", value=t("search.style.freestyle")),
            t("search.filter.distance", value=t("search.distance.value", distance=100)),
        ]
        start_label = datetime(2024, 1, 1).strftime("%d.%m.%Y")
        end_label = datetime(2024, 2, 1).strftime("%d.%m.%Y")
        date_value = t("search.filter.date_range", start=start_label, end=end_label)
        expected_entries.append(t("search.filter.dates", value=date_value))
        expected_entries.append(t("search.filter.pr_only"))
        for expected in expected_entries:
            assert expected in message_text
        assert t("search.page", cur=1, total=2) in message_text

        report_texts = [
            button.text for row in markup.inline_keyboard[:-1] for button in row
        ]
        assert report_texts == [t("search.report_btn", idx=idx) for idx in range(1, 6)]
        nav_row = markup.inline_keyboard[-1]
        assert [button.text for button in nav_row] == [t("search.next")]

        nav_cb = DummyCallback(DummyMessage())
        await paginate(nav_cb, state, SearchPageCB(page=2), query_service)

        args, kwargs = nav_cb.message.edit_text.await_args
        page_two_text = args[0]
        page_two_markup = kwargs["reply_markup"]
        assert t("search.page", cur=2, total=2) in page_two_text
        assert page_two_markup.inline_keyboard[0][0].text == t(
            "search.report_btn", idx=6
        )
        assert [button.text for button in page_two_markup.inline_keyboard[-1]] == [
            t("search.prev")
        ]

    token = set_context_language(lang)
    try:
        asyncio.run(scenario())
    finally:
        reset_context_language(token)
