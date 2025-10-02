from __future__ import annotations

import asyncio
import sqlite3
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from handlers.search import (
    SearchStates,
    input_dates,
    paginate,
    select_athlete,
    select_distance,
    select_pr,
    select_style,
    start_search,
)
from i18n import t
from keyboards import SearchFilterCB, SearchPageCB
from services.query_service import QueryService, SearchFilters, SearchPage, SearchResult


def _make_state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=99, user_id=99)
    return FSMContext(storage=storage, key=key)


def _seed_results(
    db_path: Path, rows: Sequence[tuple[int, str, str, int, float, str, bool]]
) -> None:
    with sqlite3.connect(db_path) as conn:
        for athlete_id, name, stroke, distance, total, timestamp, is_pr in rows:
            conn.execute(
                """
                INSERT INTO results (athlete_id, athlete_name, stroke, distance, total_seconds, timestamp, is_pr)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (athlete_id, name, stroke, distance, total, timestamp, int(is_pr)),
            )
        conn.commit()


class DummyMessage:
    def __init__(self, text: str = "", user_id: int = 99, chat_id: int = 42) -> None:
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


class FakeRoleService:
    def __init__(self) -> None:
        self._users = (
            SimpleNamespace(telegram_id=1, full_name="User One"),
            SimpleNamespace(telegram_id=2, full_name="User Two"),
        )

    async def get_accessible_athletes(self, requester_id: int) -> Sequence[int]:
        return (1, 2)

    async def list_users(
        self, roles: Sequence[str] | None = None
    ) -> Sequence[SimpleNamespace]:
        return self._users


class FakeQueryService:
    def __init__(self, pages: dict[int, SearchPage]) -> None:
        self._pages = pages
        self.calls: list[tuple[SearchFilters, int, int]] = []

    async def search_results(
        self, filters: SearchFilters, *, page: int, page_size: int
    ) -> SearchPage:
        self.calls.append((filters, page, page_size))
        if page in self._pages:
            return self._pages[page]
        return next(iter(self._pages.values()))


def test_query_service_filters(tmp_path: Path) -> None:
    async def scenario() -> None:
        db_path = tmp_path / "results.db"
        service = QueryService(db_path)
        await service.init()
        _seed_results(
            db_path,
            [
                (
                    1,
                    "User One",
                    "freestyle",
                    100,
                    70.5,
                    datetime(2024, 1, 10, 10, 0).isoformat(),
                    True,
                ),
                (
                    1,
                    "User One",
                    "freestyle",
                    200,
                    150.0,
                    datetime(2024, 2, 5, 9, 0).isoformat(),
                    False,
                ),
                (
                    2,
                    "User Two",
                    "backstroke",
                    100,
                    72.0,
                    datetime(2024, 1, 15, 11, 0).isoformat(),
                    True,
                ),
            ],
        )
        filters = SearchFilters(
            athlete_id=1,
            stroke="freestyle",
            distance=100,
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 31),
            only_pr=True,
        )
        page = await service.search_results(filters, page=1, page_size=5)
        assert page.total == 1
        assert len(page.items) == 1
        result = page.items[0]
        assert result.athlete_id == 1
        assert result.is_pr is True
        assert result.distance == 100

    asyncio.run(scenario())


def test_query_service_pagination(tmp_path: Path) -> None:
    async def scenario() -> None:
        db_path = tmp_path / "results.db"
        service = QueryService(db_path)
        await service.init()
        rows = [
            (
                1,
                "User One",
                "freestyle",
                50,
                30.0 + idx,
                datetime(2024, 1, 1 + idx, 8, 0).isoformat(),
                bool(idx % 2),
            )
            for idx in range(7)
        ]
        _seed_results(db_path, rows)
        filters = SearchFilters(athlete_id=1)
        page1 = await service.search_results(filters, page=1, page_size=5)
        assert page1.total == 7
        assert page1.pages == 2
        assert len(page1.items) == 5
        page2 = await service.search_results(filters, page=2, page_size=5)
        assert page2.page == 2
        assert len(page2.items) == 2
        assert page2.items[0].timestamp >= page2.items[1].timestamp

    asyncio.run(scenario())


def test_search_wizard_flow() -> None:
    async def scenario() -> None:
        state = _make_state()
        role_service = FakeRoleService()
        pages = {
            1: SearchPage(
                items=(
                    SearchResult(
                        result_id=10,
                        athlete_id=1,
                        athlete_name="User One",
                        stroke="freestyle",
                        distance=100,
                        total_seconds=70.5,
                        timestamp=datetime(2024, 1, 10, 10, 0),
                        is_pr=True,
                    ),
                    SearchResult(
                        result_id=11,
                        athlete_id=1,
                        athlete_name="User One",
                        stroke="freestyle",
                        distance=100,
                        total_seconds=71.2,
                        timestamp=datetime(2024, 1, 5, 9, 0),
                        is_pr=False,
                    ),
                ),
                total=3,
                page=1,
                pages=2,
            ),
            2: SearchPage(
                items=(
                    SearchResult(
                        result_id=12,
                        athlete_id=1,
                        athlete_name="User One",
                        stroke="freestyle",
                        distance=100,
                        total_seconds=72.0,
                        timestamp=datetime(2023, 12, 25, 18, 0),
                        is_pr=False,
                    ),
                ),
                total=3,
                page=2,
                pages=2,
            ),
        }
        query_service = FakeQueryService(pages)

        start_msg = DummyMessage(text="/search")
        await start_search(start_msg, state, role_service)
        assert await state.get_state() == SearchStates.choose_athlete.state
        start_msg.answer.assert_called_once()

        athlete_cb = DummyCallback(DummyMessage())
        await select_athlete(
            athlete_cb, state, SearchFilterCB(field="athlete", value="1")
        )
        assert await state.get_state() == SearchStates.choose_style.state
        athlete_cb.answer.assert_awaited()

        style_cb = DummyCallback(DummyMessage())
        await select_style(
            style_cb, state, SearchFilterCB(field="stroke", value="freestyle")
        )
        assert await state.get_state() == SearchStates.choose_distance.state
        style_cb.answer.assert_awaited()

        distance_cb = DummyCallback(DummyMessage())
        await select_distance(
            distance_cb, state, SearchFilterCB(field="distance", value="100")
        )
        assert await state.get_state() == SearchStates.enter_dates.state
        distance_cb.answer.assert_awaited()

        await input_dates(DummyMessage("2024-01-01 2024-02-01"), state)
        assert await state.get_state() == SearchStates.choose_pr.state

        pr_cb_message = DummyMessage()
        pr_cb = DummyCallback(pr_cb_message)
        await select_pr(
            pr_cb, state, SearchFilterCB(field="pr", value="only"), query_service
        )
        assert await state.get_state() == SearchStates.browsing.state
        pr_cb.answer.assert_awaited()
        pr_cb_message.answer.assert_called_once()

        filters, page_number, page_size = query_service.calls[0]
        assert page_number == 1 and page_size == 5
        assert filters.athlete_id == 1
        assert filters.stroke == "freestyle"
        assert filters.distance == 100
        assert filters.only_pr is True

        text = pr_cb_message.answer.await_args[0][0]
        assert t("search.page", cur=1, total=2) in text
        assert "PR" in text

        markup = pr_cb_message.answer.await_args[1]["reply_markup"]
        assert markup is not None
        assert len(markup.inline_keyboard) >= 1

        nav_cb = DummyCallback(DummyMessage())
        await paginate(nav_cb, state, SearchPageCB(page=2), query_service)
        assert query_service.calls[-1][1] == 2
        nav_cb.answer.assert_awaited()
        nav_cb.message.edit_text.assert_called_once()

    asyncio.run(scenario())
