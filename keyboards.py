from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class StrokeCB(CallbackData, prefix="stroke"):
    stroke: str


def get_stroke_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard for stroke selection."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Вольный стиль", callback_data=StrokeCB(stroke="freestyle").pack()
    )
    builder.button(text="Баттерфляй", callback_data=StrokeCB(stroke="butterfly").pack())
    builder.button(text="Брасс", callback_data=StrokeCB(stroke="breaststroke").pack())
    builder.button(text="На спине", callback_data=StrokeCB(stroke="backstroke").pack())
    builder.adjust(2)
    return builder.as_markup()
