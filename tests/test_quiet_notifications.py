import asyncio
from asyncio import QueueEmpty

import pytest

import notifications


class DummyBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, dict[str, object]]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
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


def test_send_notification_queues_during_quiet_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        async def always_quiet(*_: object, **__: object) -> bool:
            return True

        monkeypatch.setattr(notifications, "is_quiet_now", always_quiet)

        bot = DummyBot()
        await notifications.send_notification(bot, 123, "hello")

        assert bot.sent == []
        assert notifications.NOTIFICATION_QUEUE.qsize() == 1

    asyncio.run(scenario())


def test_send_notification_sends_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        async def never_quiet(*_: object, **__: object) -> bool:
            return False

        monkeypatch.setattr(notifications, "is_quiet_now", never_quiet)

        bot = DummyBot()
        await notifications.send_notification(bot, 321, "hi")

        assert notifications.NOTIFICATION_QUEUE.empty()
        assert bot.sent == [(321, "hi", {})]

    asyncio.run(scenario())


def test_drain_queue_flushes_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        async def always_quiet(*_: object, **__: object) -> bool:
            return True

        bot = DummyBot()
        monkeypatch.setattr(notifications, "is_quiet_now", always_quiet)
        await notifications.send_notification(bot, 11, "queued")

        async def never_quiet(*_: object, **__: object) -> bool:
            return False

        monkeypatch.setattr(notifications, "is_quiet_now", never_quiet)
        task = asyncio.create_task(notifications.drain_queue(interval=0.01))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert notifications.NOTIFICATION_QUEUE.empty()
        assert bot.sent == [(11, "queued", {})]

    asyncio.run(scenario())
