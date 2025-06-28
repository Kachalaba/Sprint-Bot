import logging
from aiogram import types, Router, F
from aiogram.filters.exception import ExceptionTypeFilter
from aiogram.exceptions import TelegramAPIError

router = Router()

@router.error(ExceptionTypeFilter(Exception), -F.exception(TelegramAPIError))
async def handle_any_exception(event: types.ErrorEvent):
    """
    Обработчик для любых непредвиденных ошибок в коде.
    """
    exception_name = type(event.exception).__name__
    logging.error(f"Критическая ошибка: {exception_name}: {event.exception}", exc_info=True)

    if event.update.message:
        await event.update.message.answer(
            "Ой, щось пішло не так... 😟\n"
            "Виникла непередбачена помилка. Спробуйте, будь ласка, пізніше."
        )

@router.error(ExceptionTypeFilter(TelegramAPIError))
async def handle_telegram_api_error(event: types.ErrorEvent):
    """
    Обработчик для ошибок, когда Telegram API возвращает ошибку.
    """
    logging.error(f"Помилка API Telegram: {event.exception}")
