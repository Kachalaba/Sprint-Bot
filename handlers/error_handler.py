from __future__ import annotations

import logging

from aiogram import Router, types

router = Router()


@router.errors(Exception)
async def global_error_handler(update: types.Update, exception: Exception) -> bool:
    """Handle unexpected exceptions and notify user."""

    logging.error("Unhandled exception", exc_info=True)

    message = None
    if isinstance(update, types.Message):
        message = update
    elif isinstance(update, types.CallbackQuery):
        message = update.message

    if message:
        await message.answer(
            "Произошла непредвиденная ошибка. Мы уже работаем над этим. Пожалуйста, попробуйте позже."
        )

    return True
