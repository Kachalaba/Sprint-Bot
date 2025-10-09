from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, Iterable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.types import BotCommand, Message, TelegramObject

from i18n import t
from utils.logger import get_logger
from utils.sentry import init_sentry

if TYPE_CHECKING:
    from backup_service import BackupService
    from notifications import NotificationService
    from services.turn_service import TurnService

logger = get_logger(__name__)

_SENTRY_ENABLED = init_sentry()
if _SENTRY_ENABLED:
    logger.info("Sentry successfully initialised")
else:
    logger.info("Sentry DSN not provided; Sentry disabled")


Handler = Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]]


class CommandLoggingMiddleware(BaseMiddleware):
    """Emit structured logs around command handler execution."""

    def __init__(self, logger_instance):
        self._logger = logger_instance

    async def __call__(
        self, handler: Handler, event: TelegramObject, data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message) and event.text and event.text.startswith("/"):
            user = event.from_user
            user_id = user.id if user else None
            cmd = event.text.split()[0]
            start = perf_counter()
            self._logger.info(
                "command_start",
                extra={"user_id": user_id, "cmd": cmd, "latency_ms": None},
            )
            try:
                return await handler(event, data)
            finally:
                latency_ms = (perf_counter() - start) * 1000
                self._logger.info(
                    "command_complete",
                    extra={
                        "user_id": user_id,
                        "cmd": cmd,
                        "latency_ms": round(latency_ms, 2),
                    },
                )
        return await handler(event, data)


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
        _build_bot_commands(get_bot_command_translations(lang=_DEFAULT_LANGUAGE))
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
    turn_service: "TurnService",
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
    dp.update.middleware(CommandLoggingMiddleware(logger))
    try:
        dp.workflow_data.update(turn_service=turn_service)
    except AttributeError:
        dp.workflow_data = {"turn_service": turn_service}
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
    from notifications import NotificationService, drain_queue
    from role_service import RoleService
    from services import ADMIN_IDS, TurnService, get_bot
    from services.audit_service import AuditService
    from services.io_service import IOService
    from services.query_service import QueryService
    from services.stats_service import StatsService
    from services.user_service import UserService
    from template_service import TemplateService

    bot = get_bot()
    turn_service = TurnService()
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
    dp = setup_dispatcher(notification_service, backup_service, turn_service)
    dp.update.middleware(RoleMiddleware(role_service))
    await configure_bot_commands(bot)
    queue_task = asyncio.create_task(drain_queue(), name="notification-queue-drain")
    try:
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
            turn_service=turn_service,
        )
    finally:
        queue_task.cancel()
        with suppress(asyncio.CancelledError):
            await queue_task
        await bot.session.close()
        get_bot.cache_clear()


if __name__ == "__main__":
    asyncio.run(main())
