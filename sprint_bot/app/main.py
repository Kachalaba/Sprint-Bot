"""Entry point that wires the Container to aiogram polling."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.types import Message, TelegramObject
from aiohttp import client_exceptions as aiohttp_exceptions

from notifications import drain_queue
from utils.logger import get_logger

from .container import Container

logger = get_logger(__name__)

_POLLING_INITIAL_BACKOFF = 1.0
_POLLING_MAX_BACKOFF = 60.0
_POLLING_MAX_TRIES_BEFORE_WARNING = 10
_POLLING_WARNING_SLEEP = 300.0

ClientConnectorError = aiohttp_exceptions.ClientConnectorError
ServerDisconnectedError = aiohttp_exceptions.ServerDisconnectedError
RequestTimeoutError = getattr(
    aiohttp_exceptions,
    "RequestTimeoutError",
    getattr(aiohttp_exceptions, "ServerTimeoutError", asyncio.TimeoutError),
)

_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    TelegramNetworkError,
    ServerDisconnectedError,
    RequestTimeoutError,
    ClientConnectorError,
)


Handler = Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]]
ContainerFactory = Callable[[], Awaitable[Container]]
DispatcherFactory = Callable[[Container], Dispatcher]


class CommandLoggingMiddleware(BaseMiddleware):
    """Emit structured logs around command handler execution."""

    def __init__(self, logger_instance) -> None:
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


def setup_dispatcher(container: Container) -> Dispatcher:
    """Configure the aiogram Dispatcher and register all handler routers."""

    from handlers.add_wizard import router as add_wizard_router
    from handlers.admin import router as admin_router
    from handlers.admin_browser import router as admin_browser_router
    from handlers.admin_history import router as admin_history_router
    from handlers.backup import router as backup_router
    from handlers.common import router as common_router
    from handlers.compare import router as compare_router
    from handlers.error_handler import router as error_router
    from handlers.export_analysis import router as export_analysis_router
    from handlers.export_import import router as export_import_router
    from handlers.export_reports import router as export_reports_router
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
    from middlewares.roles import RoleMiddleware

    dp = Dispatcher()
    dp.update.middleware(CommandLoggingMiddleware(logger))
    dp.update.middleware(RoleMiddleware(container.role_service))
    try:
        dp.workflow_data.update(turn_service=container.turn_service)
    except AttributeError:
        dp.workflow_data = {"turn_service": container.turn_service}

    routers = (
        registration_router,
        onboarding_router,
        menu_router,
        common_router,
        add_wizard_router,
        admin_router,
        admin_browser_router,
        admin_history_router,
        progress_router,
        compare_router,
        leaderboard_router,
        reports_router,
        export_import_router,
        export_reports_router,
        export_analysis_router,
        search_router,
        results_router,
        sprint_router,
        templates_router,
        messages_router,
        notifications_router,
        backup_router,
        error_router,
    )
    for router in routers:
        dp.include_router(router)

    dp.startup.register(container.notification_service.startup)
    dp.startup.register(container.backup_service.startup)
    dp.shutdown.register(container.notification_service.shutdown)
    dp.shutdown.register(container.backup_service.shutdown)
    return dp


async def _start_polling_with_retries(
    dp: Dispatcher,
    bot_instance: Bot,
    **polling_kwargs: Any,
) -> None:
    """Start polling and retry through transient network failures."""

    attempt = 0
    while True:
        try:
            await dp.start_polling(bot_instance, **polling_kwargs)
            break
        except asyncio.CancelledError:
            raise
        except _NETWORK_ERRORS:
            attempt += 1
            effective_attempt = min(attempt, _POLLING_MAX_TRIES_BEFORE_WARNING)
            backoff_delay = min(
                _POLLING_MAX_BACKOFF,
                _POLLING_INITIAL_BACKOFF * 2 ** (effective_attempt - 1),
            )
            logger.exception(
                "[SprintBot] polling interrupted by network error (attempt %s)",
                attempt,
            )
            if attempt > _POLLING_MAX_TRIES_BEFORE_WARNING:
                cooldown = min(_POLLING_WARNING_SLEEP, backoff_delay * 2)
                logger.warning(
                    "[SprintBot] exceeded %s polling retries; "
                    "next attempt in %s seconds",
                    _POLLING_MAX_TRIES_BEFORE_WARNING,
                    cooldown,
                )
                await asyncio.sleep(cooldown)
            else:
                await asyncio.sleep(backoff_delay)


async def run(
    *,
    container: Container | None = None,
    container_factory: ContainerFactory | None = None,
    dispatcher_factory: DispatcherFactory | None = None,
) -> None:
    """Compose the application and drive long polling until cancellation."""

    from bot import _resolve_timeout_seconds, configure_bot_commands

    logger.info("[SprintBot] starting…")

    if container is None:
        factory = container_factory or Container.build
        container = await factory()

    dp = (dispatcher_factory or setup_dispatcher)(container)

    try:
        await configure_bot_commands(container.bot)
    except TelegramRetryAfter:
        pass

    polling_kwargs = container.polling_kwargs()
    timeout_seconds = _resolve_timeout_seconds(
        getattr(container.bot.session, "timeout", None)
    )
    if timeout_seconds is not None:
        polling_kwargs["polling_timeout"] = timeout_seconds
        polling_kwargs["request_timeout"] = timeout_seconds

    queue_task = asyncio.create_task(drain_queue(), name="notification-queue-drain")
    try:
        await _start_polling_with_retries(dp, container.bot, **polling_kwargs)
    finally:
        queue_task.cancel()
        with suppress(asyncio.CancelledError):
            await queue_task
        await container.shutdown()


__all__ = [
    "CommandLoggingMiddleware",
    "Handler",
    "ContainerFactory",
    "DispatcherFactory",
    "run",
    "setup_dispatcher",
]
