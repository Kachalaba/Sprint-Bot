from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

from handlers import menu


class _DummyCallback:
    def __init__(self, message: object) -> None:
        self.message = message
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


def test_menu_progress_redirect_forwards_stats_service(monkeypatch) -> None:
    calls: list[tuple[object, object, object]] = []

    async def fake_cmd_progress(
        message: object, role_service: object, stats_service: object
    ) -> None:
        calls.append((message, role_service, stats_service))

    fake_progress_module = ModuleType("handlers.progress")
    fake_progress_module.cmd_progress = fake_cmd_progress
    monkeypatch.setitem(sys.modules, "handlers.progress", fake_progress_module)

    role_service = SimpleNamespace()
    stats_service = SimpleNamespace()
    callback = _DummyCallback(message=SimpleNamespace())

    asyncio.run(menu.menu_progress_redirect(callback, role_service, stats_service))

    assert calls == [(callback.message, role_service, stats_service)]
    assert callback.answered
