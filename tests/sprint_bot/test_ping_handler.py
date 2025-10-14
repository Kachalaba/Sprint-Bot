"""Tests for the ping router running through aiogram dispatcher."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import pytest
from aiogram import Dispatcher
from aiogram.client.bot import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage
from aiogram.methods.base import TelegramMethod
from aiogram.types import Update

from sprint_bot.application.handlers import ping as ping_module
from sprint_bot.infrastructure.storage.google_sheets import GoogleSheetsStorage
from tests.fakes import SheetsClientFake


class TelegramSessionFake(BaseSession):
    """Minimal Telegram session collecting requests for assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod] = []

    async def close(self) -> None:
        return None

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod,
        timeout: int | None = None,
    ) -> object:
        self.requests.append(method)
        if isinstance(method, SendMessage):
            payload = {
                "message_id": len(self.requests),
                "date": int(datetime.now().timestamp()),
                "chat": {"id": method.chat_id, "type": "private"},
                "text": method.text,
            }
            return method.__returning__.model_validate(payload)
        return method.__returning__.model_construct()

    async def stream_content(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        if False:  # pragma: no cover - streaming not used in tests
            yield b""
        return


@pytest.fixture()
def ping_storage() -> GoogleSheetsStorage:
    """Return storage fixture with populated worksheets."""

    client = SheetsClientFake()
    client.register_spreadsheet(
        "test",
        {
            "AthletesList": [
                {
                    "id": "athlete-001",
                    "full_name": "Alice Runner",
                    "telegram_id": 1001,
                    "is_active": True,
                }
            ],
            "results": [
                {
                    "id": "race-001",
                    "athlete_id": "athlete-001",
                    "event_date": "2024-06-01",
                    "name": "Summer Sprint",
                    "distance_m": "5000",
                    "official_time": "00:18:30",
                    "split1_time": "00:06:00",
                    "split1_distance": "2000",
                    "split2_time": "00:06:15",
                    "split2_distance": "2000",
                    "split3_time": "00:06:15",
                    "split3_distance": "1000",
                }
            ],
        },
    )
    storage = GoogleSheetsStorage(
        spreadsheet_key="test",
        credentials_path=Path("/tmp/credentials.json"),
    )
    storage._client = client  # type: ignore[attr-defined]
    storage._spreadsheet = client.open_by_key("test")  # type: ignore[attr-defined]
    return storage


@pytest.mark.asyncio()
async def test_ping_handler_dispatch(ping_storage: GoogleSheetsStorage) -> None:
    session = TelegramSessionFake()
    bot = Bot(token="42:TEST", session=session)

    dp = Dispatcher()
    dp.include_router(ping_module.router)
    dp["storage"] = ping_storage

    update = Update.model_validate(
        {
            "update_id": 1000,
            "message": {
                "message_id": 1,
                "date": int(datetime.now().timestamp()),
                "chat": {"id": 500, "type": "private"},
                "from": {"id": 500, "is_bot": False, "first_name": "Tester"},
                "text": "/ping",
            },
        }
    )

    await dp.feed_update(bot, update)

    assert session.requests, "expected sendMessage call"
    request = session.requests[0]
    assert isinstance(request, SendMessage)
    assert "PONG" in request.text
    assert "athletes=1" in request.text
    assert "splits=3" in request.text
