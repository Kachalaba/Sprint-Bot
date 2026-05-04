"""Sprint Bot entry point — delegates wiring to ``sprint_bot.app``."""

from __future__ import annotations

import asyncio
from typing import Any, Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import BotCommand
from aiohttp import ClientTimeout

from i18n import t
from utils.logger import get_logger
from utils.sentry import init_sentry

logger = get_logger(__name__)

_SENTRY_ENABLED = init_sentry()
if _SENTRY_ENABLED:
    logger.info("Sentry successfully initialised")
else:
    logger.info("Sentry DSN not provided; Sentry disabled")


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
    try:
        await bot_instance.set_my_commands(default_commands)

        for language in SUPPORTED_LANGUAGES:
            if language == _DEFAULT_LANGUAGE:
                continue
            commands = list(
                _build_bot_commands(get_bot_command_translations(lang=language))
            )
            await bot_instance.set_my_commands(commands, language_code=language)
    except TelegramRetryAfter as exc:
        logger.warning(
            "[config] FLOOD: commands were not updated, wait %s seconds",
            exc.timeout,
        )


def _resolve_timeout_seconds(timeout_obj: Any) -> float | None:
    """Return timeout seconds from ``ClientTimeout`` or primitives."""

    if timeout_obj is None:
        return None
    if isinstance(timeout_obj, (int, float)):
        return float(timeout_obj) if timeout_obj > 0 else None
    if isinstance(timeout_obj, ClientTimeout):
        candidates = [
            getattr(timeout_obj, "total", None),
            getattr(timeout_obj, "total_timeout", None),
            getattr(timeout_obj, "sock_read", None),
            getattr(timeout_obj, "sock_connect", None),
            getattr(timeout_obj, "connect", None),
        ]
        for candidate in candidates:
            if isinstance(candidate, (int, float)) and candidate > 0:
                return float(candidate)
        return None
    numeric_value = getattr(timeout_obj, "total", None)
    if isinstance(numeric_value, (int, float)) and numeric_value > 0:
        return float(numeric_value)
    return None


async def main() -> None:
    """Start Sprint Bot via the application composition root."""

    from sprint_bot.app import run

    await run()


if __name__ == "__main__":
    asyncio.run(main())
