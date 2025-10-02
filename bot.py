from __future__ import annotations

import asyncio
import logging
import os
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from typing import TYPE_CHECKING, Iterable

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from i18n import t

if TYPE_CHECKING:
    from backup_service import BackupService
    from notifications import NotificationService

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.WARNING)
stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))

logger.addHandler(file_handler)
logger.addHandler(stream_handler)


SUPPORTED_LANGUAGES: tuple[str, ...] = ("uk", "ru")
_DEFAULT_LANGUAGE = "uk"

_START_MESSAGE_KEY = "bot.start_welcome"
_HELP_MESSAGE_KEY = "bot.help"
_UNKNOWN_COMMAND_KEY = "bot.unknown_command"
_COMMAND_KEYS: dict[str, str] = {
    "start": "bot.cmd.start",
    "help": "bot.cmd.help",
    "menu": "bot.cmd.menu",
}


def get_start_message(*, lang: str | None = None) -> str:
    """Return localized welcome message for ``/start`` command."""

    return t(_START_MESSAGE_KEY, lang=lang)


def get_help_message(*, lang: str | None = None) -> str:
    """Return localized help message for ``/help`` command."""

    return t(_HELP_MESSAGE_KEY, lang=lang)


def get_unknown_command_message(*, lang: str | None = None) -> str:
    """Return localized fallback message for unknown commands."""

    return t(_UNKNOWN_COMMAND_KEY, lang=lang)


def get_bot_command_translations(*, lang: str) -> dict[str, str]:
    """Return mapping of bot commands to localized descriptions."""

    return {command: t(key, lang=lang) for command, key in _COMMAND_KEYS.items()}


def _build_bot_commands(descriptions: dict[str, str]) -> Iterable[BotCommand]:
    for command, description in descriptions.items():
        yield BotCommand(command=command, description=description)


async def configure_bot_commands(bot_instance: Bot) -> None:
    """Configure command list for supported languages."""

    default_commands = list(
        _build_bot_commands(
            get_bot_command_translations(lang=_DEFAULT_LANGUAGE)
        )
    )
    await bot_instance.set_my_commands(default_commands)

    for language in SUPPORTED_LANGUAGES:
        if language == _DEFAULT_LANGUAGE:
            continue
        commands = list(
            _build_bot_commands(get_bot_command_translations(lang=language))
        )
        await bot_instance.set_my_commands(commands, language_code=language)


def _parse_admin_chat_ids(admin_ids_source: Iterable[str]) -> tuple[int, ...]:
    ids: list[int] = []
    for raw_id in admin_ids_source:
        raw_id = raw_id.strip()
        if not raw_id:
            continue
        try:
            ids.append(int(raw_id))
        except ValueError:
            logger.warning("Invalid ADMIN_IDS entry skipped: %s", raw_id)
    return tuple(ids)


def _backup_interval_from_env(default_hours: float = 6.0) -> timedelta:
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


def setup_dispatcher(
    notification_service: "NotificationService",
    backup_service: "BackupService",
) -> Dispatcher:
    """Configure dispatcher with routers."""
    from handlers.add_wizard import router as add_wizard_router
    from handlers.admin import router as admin_router
    from handlers.admin_history import router as admin_history_router
    from handlers.backup import router as backup_router
    from handlers.common import router as common_router
    from handlers.error_handler import router as error_router
    from handlers.export_import import router as export_import_router
    from handlers.leaderboard import router as leaderboard_router
    from handlers.menu import router as menu_router
    from handlers.messages import router as messages_router
    from handlers.notifications import router as notifications_router
    from handlers.onboarding import router as onboarding_router
    from handlers.progress import router as progress_router
    from handlers.registration import router as registration_router
    from handlers.reports import router as reports_router
    from handlers.results import router as results_router
    from handlers.search import router as search_router
    from handlers.sprint_actions import router as sprint_router
    from handlers.templates import router as templates_router

    dp = Dispatcher()
    dp.include_router(registration_router)
    dp.include_router(onboarding_router)
    dp.include_router(menu_router)
    dp.include_router(common_router)
    dp.include_router(add_wizard_router)
    dp.include_router(admin_router)
    dp.include_router(admin_history_router)
    dp.include_router(progress_router)
    dp.include_router(leaderboard_router)
    dp.include_router(reports_router)
    dp.include_router(export_import_router)
    dp.include_router(search_router)
    dp.include_router(results_router)
    dp.include_router(sprint_router)
    dp.include_router(templates_router)
    dp.include_router(messages_router)
    dp.include_router(notifications_router)
    dp.include_router(backup_router)
    dp.include_router(error_router)
    dp.startup.register(notification_service.startup)
    dp.startup.register(backup_service.startup)
    dp.shutdown.register(notification_service.shutdown)
    dp.shutdown.register(backup_service.shutdown)
    return dp


async def main() -> None:
    """Start Sprint Bot."""
    logger.info("[SprintBot] starting…")
    from backup_service import BackupService
    from chat_service import DB_PATH, ChatService
    from middlewares.roles import RoleMiddleware
    from notifications import NotificationService
    from role_service import RoleService
    from services import ADMIN_IDS, bot
    from services.audit_service import AuditService
    from services.io_service import IOService
    from services.query_service import QueryService
    from services.stats_service import StatsService
    from services.user_service import UserService
    from template_service import TemplateService

    notification_service = NotificationService(bot=bot)
    chat_service = ChatService()
    await chat_service.init()
    admin_chat_ids = _parse_admin_chat_ids(ADMIN_IDS)
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
        bot=bot,
        db_path=Path(os.getenv("CHAT_DB_PATH", DB_PATH)),
        bucket_name=os.getenv("S3_BACKUP_BUCKET", ""),
        backup_prefix=os.getenv("S3_BACKUP_PREFIX", "sprint-bot/backups/"),
        interval=_backup_interval_from_env(),
        admin_chat_ids=admin_chat_ids,
        storage_class=os.getenv("S3_STORAGE_CLASS") or None,
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
    )
    dp = setup_dispatcher(notification_service, backup_service)
    dp.update.middleware(RoleMiddleware(role_service))
    await configure_bot_commands(bot)
    await dp.start_polling(
        bot,
        notifications=notification_service,
        chat_service=chat_service,
        backup_service=backup_service,
        role_service=role_service,
        user_service=user_service,
        template_service=template_service,
        query_service=query_service,
        stats_service=stats_service,
        io_service=io_service,
        audit_service=audit_service,
    )


if __name__ == "__main__":
    asyncio.run(main())
