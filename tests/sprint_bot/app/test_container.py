"""Container wiring tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from sprint_bot.app.container import (
    Container,
    _backup_interval_from_env,
    _parse_admin_chat_ids,
)


def _make_container() -> Container:
    bot = MagicMock()
    bot.close = AsyncMock()
    bot.session = MagicMock()
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
        admin_chat_ids=(123, 456),
    )


class TestParseAdminChatIds:
    def test_csv_parsed(self) -> None:
        assert _parse_admin_chat_ids(["1", "2", "3"]) == (1, 2, 3)

    def test_blank_skipped(self) -> None:
        assert _parse_admin_chat_ids(["1", "", "  ", "2"]) == (1, 2)

    def test_invalid_skipped(self) -> None:
        assert _parse_admin_chat_ids(["1", "abc", "2", "3.5"]) == (1, 2)

    def test_empty_input(self) -> None:
        assert _parse_admin_chat_ids([]) == ()


class TestBackupIntervalFromEnv:
    def test_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BACKUP_INTERVAL_HOURS", raising=False)
        assert _backup_interval_from_env() == timedelta(hours=6.0)

    def test_custom_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BACKUP_INTERVAL_HOURS", raising=False)
        assert _backup_interval_from_env(default_hours=12.0) == timedelta(hours=12.0)

    def test_valid_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BACKUP_INTERVAL_HOURS", "2.5")
        assert _backup_interval_from_env() == timedelta(hours=2.5)

    def test_invalid_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BACKUP_INTERVAL_HOURS", "not-a-number")
        assert _backup_interval_from_env() == timedelta(hours=6.0)

    def test_zero_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BACKUP_INTERVAL_HOURS", "0")
        assert _backup_interval_from_env() == timedelta(hours=6.0)

    def test_negative_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BACKUP_INTERVAL_HOURS", "-3")
        assert _backup_interval_from_env() == timedelta(hours=6.0)


class TestContainerPollingKwargs:
    def test_includes_all_services(self) -> None:
        container = _make_container()
        kwargs = container.polling_kwargs()
        assert kwargs["notifications"] is container.notification_service
        assert kwargs["chat_service"] is container.chat_service
        assert kwargs["backup_service"] is container.backup_service
        assert kwargs["role_service"] is container.role_service
        assert kwargs["user_service"] is container.user_service
        assert kwargs["template_service"] is container.template_service
        assert kwargs["query_service"] is container.query_service
        assert kwargs["stats_service"] is container.stats_service
        assert kwargs["io_service"] is container.io_service
        assert kwargs["audit_service"] is container.audit_service
        assert kwargs["turn_service"] is container.turn_service

    def test_does_not_leak_bot_or_admin_ids(self) -> None:
        container = _make_container()
        kwargs = container.polling_kwargs()
        assert "bot" not in kwargs
        assert "admin_chat_ids" not in kwargs


class TestContainerShutdown:
    @pytest.mark.asyncio
    async def test_closes_bot_and_session(self) -> None:
        container = _make_container()
        await container.shutdown()
        container.bot.close.assert_awaited_once()
        container.bot.session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_swallows_close_errors(self) -> None:
        container = _make_container()
        container.bot.close = AsyncMock(side_effect=RuntimeError("boom"))
        container.bot.session.close = AsyncMock(side_effect=RuntimeError("boom"))
        await container.shutdown()
