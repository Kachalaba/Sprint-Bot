"""Service container that wires the production dependency graph."""

from __future__ import annotations

import os
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from aiogram import Bot

from utils.logger import get_logger

if TYPE_CHECKING:
    from backup_service import BackupService
    from chat_service import ChatService
    from notifications import NotificationService
    from role_service import RoleService
    from services.audit_service import AuditService
    from services.io_service import IOService
    from services.query_service import QueryService
    from services.stats_service import StatsService
    from services.turn_service import TurnService
    from services.user_service import UserService
    from template_service import TemplateService

logger = get_logger(__name__)

_DEFAULT_BACKUP_HOURS = 6.0


def _parse_admin_chat_ids(raw: Iterable[str]) -> tuple[int, ...]:
    """Parse the ``ADMIN_IDS`` env CSV into a tuple of integer chat ids."""

    ids: list[int] = []
    for raw_id in raw:
        cleaned = (raw_id or "").strip()
        if not cleaned:
            continue
        try:
            ids.append(int(cleaned))
        except ValueError:
            logger.warning("Invalid ADMIN_IDS entry skipped: %s", cleaned)
    return tuple(ids)


def _backup_interval_from_env(default_hours: float = _DEFAULT_BACKUP_HOURS) -> timedelta:
    """Resolve the backup cadence from ``BACKUP_INTERVAL_HOURS``."""

    value = os.getenv("BACKUP_INTERVAL_HOURS")
    if not value:
        return timedelta(hours=default_hours)
    try:
        hours = float(value)
    except ValueError:
        logger.warning("Invalid BACKUP_INTERVAL_HOURS=%s, using default", value)
        return timedelta(hours=default_hours)
    if hours <= 0:
        logger.warning(
            "Non-positive BACKUP_INTERVAL_HOURS=%s provided, using default", hours
        )
        return timedelta(hours=default_hours)
    return timedelta(hours=hours)


@dataclass
class Container:
    """Holds the initialised service graph used to drive the bot."""

    bot: Bot
    turn_service: "TurnService"
    notification_service: "NotificationService"
    chat_service: "ChatService"
    role_service: "RoleService"
    user_service: "UserService"
    audit_service: "AuditService"
    template_service: "TemplateService"
    query_service: "QueryService"
    stats_service: "StatsService"
    io_service: "IOService"
    backup_service: "BackupService"
    admin_chat_ids: tuple[int, ...] = field(default_factory=tuple)

    @classmethod
    async def build(cls, *, bot: Bot | None = None) -> "Container":
        """Construct and asynchronously initialise every dependency."""

        from backup_service import BackupService
        from chat_service import DB_PATH, ChatService
        from notifications import NotificationService
        from role_service import RoleService
        from services import ADMIN_IDS, TurnService, get_bot
        from services.audit_service import AuditService
        from services.io_service import IOService
        from services.query_service import QueryService
        from services.stats_service import StatsService
        from services.user_service import UserService
        from template_service import TemplateService

        bot_instance = bot or get_bot()
        admin_chat_ids = _parse_admin_chat_ids(ADMIN_IDS)

        turn_service = TurnService()
        notification_service = NotificationService(bot=bot_instance)

        chat_service = ChatService()
        await chat_service.init()

        role_service = RoleService()
        await role_service.init(admin_ids=admin_chat_ids)

        user_service = UserService()
        await user_service.init()

        audit_service = AuditService()
        await audit_service.init()

        template_service = TemplateService(audit_service=audit_service)
        await template_service.init()

        query_service = QueryService()
        await query_service.init()

        stats_service = StatsService()
        await stats_service.init()

        io_service = IOService(audit_service=audit_service)
        await io_service.init()

        backup_service = BackupService(
            bot=bot_instance,
            db_path=Path(os.getenv("CHAT_DB_PATH", DB_PATH)),
            bucket_name=os.getenv("S3_BACKUP_BUCKET", ""),
            backup_prefix=os.getenv("S3_BACKUP_PREFIX", "sprint-bot/backups/"),
            interval=_backup_interval_from_env(),
            admin_chat_ids=admin_chat_ids,
            storage_class=os.getenv("S3_STORAGE_CLASS") or None,
            endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        )

        return cls(
            bot=bot_instance,
            turn_service=turn_service,
            notification_service=notification_service,
            chat_service=chat_service,
            role_service=role_service,
            user_service=user_service,
            audit_service=audit_service,
            template_service=template_service,
            query_service=query_service,
            stats_service=stats_service,
            io_service=io_service,
            backup_service=backup_service,
            admin_chat_ids=admin_chat_ids,
        )

    def polling_kwargs(self) -> dict[str, Any]:
        """Mapping forwarded to ``dp.start_polling`` as middleware context."""

        return {
            "notifications": self.notification_service,
            "chat_service": self.chat_service,
            "backup_service": self.backup_service,
            "role_service": self.role_service,
            "user_service": self.user_service,
            "template_service": self.template_service,
            "query_service": self.query_service,
            "stats_service": self.stats_service,
            "io_service": self.io_service,
            "audit_service": self.audit_service,
            "turn_service": self.turn_service,
        }

    async def shutdown(self) -> None:
        """Release the Bot HTTP session and underlying connections."""

        with suppress(Exception):
            await self.bot.close()
        with suppress(Exception):
            await self.bot.session.close()


__all__ = [
    "Container",
    "_parse_admin_chat_ids",
    "_backup_interval_from_env",
]
