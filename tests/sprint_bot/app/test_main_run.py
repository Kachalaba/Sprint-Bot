"""Composition root behaviour tests for ``sprint_bot.app.main.run``."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from sprint_bot.app import main as app_main
from sprint_bot.app.container import Container


def _make_container() -> Container:
    bot = MagicMock()
    bot.close = AsyncMock()
    bot.session = MagicMock()
    bot.session.timeout = None
    bot.session.close = AsyncMock()
    return Container(
        bot=bot,
        turn_service=MagicMock(name="turn"),
        notification_service=MagicMock(name="notifications"),
        chat_service=MagicMock(name="chat"),
        role_service=MagicMock(name="role"),
        user_service=MagicMock(name="user"),
        audit_service=MagicMock(name="audit"),
        template_service=MagicMock(name="template"),
        query_service=MagicMock(name="query"),
        stats_service=MagicMock(name="stats"),
        io_service=MagicMock(name="io"),
        backup_service=MagicMock(name="backup"),
        admin_chat_ids=(),
    )


@pytest.mark.asyncio
async def test_run_uses_provided_container_and_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _make_container()
    fake_dp = MagicMock(name="dp")
    fake_dp.start_polling = AsyncMock()
    dispatcher_factory = MagicMock(return_value=fake_dp)

    drain_called = asyncio.Event()

    async def fake_drain() -> None:
        drain_called.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return

    async def fake_configure(_bot) -> None:
        return None

    monkeypatch.setattr(app_main, "drain_queue", fake_drain)

    import bot as bot_module

    monkeypatch.setattr(bot_module, "configure_bot_commands", fake_configure)

    await app_main.run(container=container, dispatcher_factory=dispatcher_factory)

    dispatcher_factory.assert_called_once_with(container)
    fake_dp.start_polling.assert_awaited_once()
    args, kwargs = fake_dp.start_polling.call_args
    assert args == (container.bot,)
    assert kwargs["notifications"] is container.notification_service
    assert kwargs["turn_service"] is container.turn_service
    container.bot.close.assert_awaited_once()
    container.bot.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_builds_via_container_factory_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _make_container()
    fake_dp = MagicMock(name="dp")
    fake_dp.start_polling = AsyncMock()

    factory = AsyncMock(return_value=container)

    async def fake_drain() -> None:
        return None

    async def fake_configure(_bot) -> None:
        return None

    monkeypatch.setattr(app_main, "drain_queue", fake_drain)
    import bot as bot_module

    monkeypatch.setattr(bot_module, "configure_bot_commands", fake_configure)

    await app_main.run(
        container_factory=factory, dispatcher_factory=lambda _: fake_dp
    )

    factory.assert_awaited_once()
    fake_dp.start_polling.assert_awaited_once()
    container.bot.close.assert_awaited_once()


def test_setup_dispatcher_registers_routers_and_workflow() -> None:
    container = _make_container()

    async def _noop() -> None:
        return None

    container.notification_service.startup = _noop
    container.notification_service.shutdown = _noop
    container.backup_service.startup = _noop
    container.backup_service.shutdown = _noop

    dp = app_main.setup_dispatcher(container)

    assert dp.workflow_data["turn_service"] is container.turn_service
    assert dp.sub_routers
