from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from handlers.leaderboard import my_progress_week, show_leaders
from services.stats_service import StatsService


class DummySentMessage:
    def __init__(self) -> None:
        self.edit_text = AsyncMock()
        self.payloads: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def _edit_text(self, *args: Any, **kwargs: Any) -> Any:
        self.payloads.append((args, kwargs))
        return None


class DummyMessage:
    def __init__(self, text: str, *, user_id: int = 1) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.sent: list[DummySentMessage] = []

        async def _answer(*_args: Any, **_kwargs: Any) -> DummySentMessage:
            sent = DummySentMessage()
            self.sent.append(sent)
            return sent

        self.answer = AsyncMock(side_effect=_answer)


def _seed_results(
    db_path: Path,
    rows: list[tuple[int, str, str, int, float, str, bool]],
) -> None:
    with sqlite3.connect(db_path) as conn:
        for athlete_id, name, stroke, distance, total, timestamp, is_pr in rows:
            conn.execute(
                """
                INSERT INTO results (
                    athlete_id, athlete_name, stroke, distance, total_seconds, timestamp, is_pr
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (athlete_id, name, stroke, distance, total, timestamp, int(is_pr)),
            )
        conn.commit()


def test_leaders_command_week(tmp_path: Path) -> None:
    async def scenario() -> None:
        db_path = tmp_path / "results.db"
        service = StatsService(db_path)
        await service.init()
        now = datetime.now(timezone.utc)
        _seed_results(
            db_path,
            [
                (
                    1,
                    "User One",
                    "freestyle",
                    100,
                    70.5,
                    (now - timedelta(days=2)).isoformat(),
                    True,
                ),
                (
                    1,
                    "User One",
                    "freestyle",
                    50,
                    31.0,
                    (now - timedelta(days=1)).isoformat(),
                    True,
                ),
                (
                    1,
                    "User One",
                    "freestyle",
                    100,
                    72.0,
                    (now - timedelta(days=1)).isoformat(),
                    False,
                ),
                (
                    2,
                    "User Two",
                    "backstroke",
                    100,
                    72.5,
                    (now - timedelta(days=3)).isoformat(),
                    True,
                ),
                (
                    3,
                    "User Three",
                    "breaststroke",
                    200,
                    150.0,
                    (now - timedelta(days=10)).isoformat(),
                    True,
                ),
            ],
        )

        message = DummyMessage("/leaders week")
        await show_leaders(message, stats_service=service)

        assert message.answer.await_count == 1
        assert len(message.sent) == 1
        final_text = message.sent[0].edit_text.call_args[0][0]
        assert final_text.startswith("🏆 Лидеры недели:")
        assert "User One — 2 PR" in final_text
        assert final_text.index("User One") < final_text.index("User Two")

    asyncio.run(scenario())


def test_my_progress_week_summary(tmp_path: Path) -> None:
    async def scenario() -> None:
        db_path = tmp_path / "results.db"
        service = StatsService(db_path)
        await service.init()
        now = datetime.now(timezone.utc)
        _seed_results(
            db_path,
            [
                (
                    5,
                    "Athlete",
                    "freestyle",
                    50,
                    30.5,
                    (now - timedelta(days=2)).isoformat(),
                    True,
                ),
                (
                    5,
                    "Athlete",
                    "backstroke",
                    50,
                    31.2,
                    (now - timedelta(days=3)).isoformat(),
                    False,
                ),
                (
                    5,
                    "Athlete",
                    "freestyle",
                    50,
                    30.2,
                    (now - timedelta(days=1)).isoformat(),
                    True,
                ),
                (
                    5,
                    "Athlete",
                    "freestyle",
                    50,
                    31.5,
                    (now - timedelta(days=12)).isoformat(),
                    False,
                ),
            ],
        )

        message = DummyMessage("/my_progress_week", user_id=5)
        await my_progress_week(message, stats_service=service)

        assert message.answer.await_count == 1
        final_text = message.sent[0].edit_text.call_args[0][0]
        assert "Попытки: 3" in final_text
        assert "PR: 2" in final_text
        assert "⭐ 50 м кроль" in final_text

    asyncio.run(scenario())
