import asyncio
import logging

from aiogram import F, Router, types
from aiogram.exceptions import TelegramAPIError
from aiogram.filters.exception import ExceptionTypeFilter

from i18n import t

router = Router()


def _resolve_error_message(exc: Exception) -> str:
    error_map: tuple[tuple[type[BaseException], str], ...] = (
        (asyncio.TimeoutError, "error.timeout"),
        (TimeoutError, "error.timeout"),
        (ValueError, "error.invalid_input"),
        (PermissionError, "error.forbidden"),
    )

    for exc_type, key in error_map:
        if isinstance(exc, exc_type):
            return t(key)

    return t("error.internal")


async def _reply_to_user(event: types.ErrorEvent, text: str) -> None:
    update = getattr(event, "update", None)
    if update is None:
        return

    callback_query = getattr(update, "callback_query", None)
    if callback_query is not None:
        try:
            await callback_query.answer(text, show_alert=True)
        except TypeError:
            await callback_query.answer(text)
        return

    message = getattr(update, "message", None)
    if message is not None:
        await message.answer(text)


@router.error(ExceptionTypeFilter(Exception), -F.exception(TelegramAPIError))
async def handle_any_exception(event: types.ErrorEvent):
    """
    Обработчик для любых непредвиденных ошибок в коде.
    """
    exception_name = type(event.exception).__name__
    logging.error(
        f"Критическая ошибка: {exception_name}: {event.exception}", exc_info=True
    )

    message_text = _resolve_error_message(event.exception)
    await _reply_to_user(event, message_text)


@router.error(ExceptionTypeFilter(TelegramAPIError))
async def handle_telegram_api_error(event: types.ErrorEvent):
    """
    Обработчик для ошибок, когда Telegram API возвращает ошибку.
    """
    logging.error(f"Помилка API Telegram: {event.exception}")
    await _reply_to_user(event, t("error.internal"))
