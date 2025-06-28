from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# --- CallbackData Factories ---

class StrokeCB(CallbackData, prefix="stroke"):
    stroke: str

# --- Reply Keyboards ---

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Додати результат ➕")],
        [KeyboardButton(text="Мої результати 🏆"), KeyboardButton(text="Особисті рекорди 🥇")],
    ],
    resize_keyboard=True,
)

# --- Inline Keyboards ---

def get_stroke_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for choosing swim stroke."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏊‍♂️ Кроль", callback_data=StrokeCB(stroke="freestyle").pack()),
                InlineKeyboardButton(text="🏊‍♀️ Спина", callback_data=StrokeCB(stroke="backstroke").pack()),
            ],
            [
                InlineKeyboardButton(text="🦋 Батерфляй", callback_data=StrokeCB(stroke="butterfly").pack()),
                InlineKeyboardButton(text="🐸 Брас", callback_data=StrokeCB(stroke="breaststroke").pack()),
            ],
        ]
    )

def get_history_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard with a button to show detailed history."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📜 Показати детальну історію", callback_data="history")
            ]
        ]
    )

def get_sportsmen_keyboard(sportsmen: list) -> InlineKeyboardMarkup:
    """Gets keyboard with sportsmen names."""
    buttons = [
        InlineKeyboardButton(text=name, callback_data=name) for name in sportsmen
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def get_distance_keyboard(distances: list) -> InlineKeyboardMarkup:
    """Gets keyboard with distances."""
    buttons = [
        InlineKeyboardButton(text=f"{dist} м", callback_data=dist) for dist in distances
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])
