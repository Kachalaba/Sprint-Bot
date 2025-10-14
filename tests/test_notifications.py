import asyncio
from asyncio import QueueEmpty
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

import pytest
from zoneinfo import ZoneInfo

import notifications


@dataclass
class DummyBot:
    sent: list[tuple[int, str, dict[str, Any]]]

    def __init__(self) -> None:
        self.sent = []

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> None:
        self.sent.append((chat_id, text, dict(kwargs)))


@pytest.fixture(autouse=True)
def clear_notification_queue() -> None:
    queue = notifications.NOTIFICATION_QUEUE
    while True:
        try:
            queue.get_nowait()
        except QueueEmpty:
            break
        else:
            queue.task_done()
    yield
    while True:
        try:
            queue.get_nowait()
        except QueueEmpty:
            break
        else:
            queue.task_done()


class ControlledDatetime(datetime):
    current: datetime = datetime(2023, 1, 1, 23, 0, tzinfo=ZoneInfo("Europe/Kyiv"))

    @classmethod
    def now(cls, tz: ZoneInfo | None = None) -> datetime:
        if tz is None:
            return cls.current
        return cls.current.astimezone(tz)

    @classmethod
    def utcnow(cls) -> datetime:
        return cls.current.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def set_time(hour: int, minute: int) -> None:
    ControlledDatetime.current = datetime(
        2023,
        1,
        1,
        hour,
        minute,
        tzinfo=ZoneInfo("Europe/Kyiv"),
    )


def test_notifications_queue_and_drain(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        monkeypatch.setattr(
            notifications,
            "QUIET_HOURS_WINDOW",
            (time(22, 0), time(6, 0)),
            raising=False,
        )
        monkeypatch.setattr(notifications, "datetime", ControlledDatetime)

        bot = DummyBot()
        set_time(23, 0)
        messages = ["first", "second", "third"]
        for text in messages:
            await notifications.send_notification(bot, 42, text)

        queue = notifications.NOTIFICATION_QUEUE
        assert queue.qsize() == len(messages)
        assert bot.sent == []

        set_time(9, 0)
        drain_task = asyncio.create_task(notifications.drain_queue(interval=0.01))
        try:
            await asyncio.sleep(0.05)
            assert queue.empty()
            assert [text for _, text, _ in bot.sent] == messages
            assert len(bot.sent) == len(messages)
        finally:
            drain_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await drain_task

    asyncio.run(scenario())


def test_trainer_notifications_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        monkeypatch.setattr(notifications, "_TRAINER_THROTTLE_SECONDS", 0.02)
        monkeypatch.setattr(notifications, "_TRAINER_DUPLICATE_TTL", 10.0)

        bot = DummyBot()
        service = notifications.NotificationService(bot)

        base_kwargs = dict(
            actor_id=222,
            actor_name="Coach",
            athlete_id=222,
            athlete_name="Athlete",
            dist=100,
            stroke="freestyle",
            total=65.0,
            timestamp="2024-01-01 10:00",
            stats={"new_total_pr": True, "total_pr_delta": 1.23, "sob_delta": 0.0},
            trainers=[111],
            new_prs=[(50, 30.0)],
        )
        second_kwargs = dict(
            base_kwargs,
            total=64.5,
            stats={"new_total_pr": True, "total_pr_delta": 0.5, "sob_delta": 0.0},
        )

        await service.notify_new_result(**base_kwargs)
        await asyncio.sleep(0.01)
        assert [item[0] for item in bot.sent] == [111]

        await service.notify_new_result(**second_kwargs)
        await asyncio.sleep(0.005)
        assert len(bot.sent) == 1  # throttled

        await asyncio.sleep(0.05)
        assert len(bot.sent) == 2

        await service.notify_new_result(**second_kwargs)
        await asyncio.sleep(0.05)
        assert len(bot.sent) == 2  # duplicate suppressed

        await service.shutdown()

    asyncio.run(scenario())
