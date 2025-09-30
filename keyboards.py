from __future__ import annotations

from typing import Iterable

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


class DistanceCB(CallbackData, prefix="dist"):
    """Callback factory for choosing a sprint distance."""

    value: int


class TemplateCB(CallbackData, prefix="tpl"):
    """Callback factory for sprint templates."""

    template_id: str


class RepeatCB(CallbackData, prefix="repeat"):
    """Callback factory for repeating the previous result."""

    athlete_id: int


class CommentCB(CallbackData, prefix="comment"):
    """Callback factory for comment management."""

    action: str
    ts: str
    athlete_id: int


# --- Reply Keyboards ---

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Додати результат ➕")],
        [
            KeyboardButton(text="Мої результати 🏆"),
            KeyboardButton(text="Особисті рекорди 🥇"),
        ],
    ],
    resize_keyboard=True,
)

# --- Inline Keyboards ---


def get_stroke_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for choosing swim stroke."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏊‍♂️ Кроль", callback_data=StrokeCB(stroke="freestyle").pack()
                ),
                InlineKeyboardButton(
                    text="🏊‍♀️ Спина", callback_data=StrokeCB(stroke="backstroke").pack()
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🦋 Батерфляй",
                    callback_data=StrokeCB(stroke="butterfly").pack(),
                ),
                InlineKeyboardButton(
                    text="🐸 Брас", callback_data=StrokeCB(stroke="breaststroke").pack()
                ),
            ],
        ]
    )


def get_history_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard with a button to show detailed history."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📜 Показати детальну історію", callback_data="history"
                )
            ]
        ]
    )


def get_sportsmen_keyboard(sportsmen: list) -> InlineKeyboardMarkup:
    """Gets keyboard with sportsmen names."""
    buttons = [
        InlineKeyboardButton(text=name, callback_data=name) for name in sportsmen
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def get_distance_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard with frequently used sprint distances."""

    distance_buttons = [
        [
            InlineKeyboardButton(
                text=f"{dist} м", callback_data=DistanceCB(value=dist).pack()
            )
            for dist in row
        ]
        for row in ((50, 100, 200), (400, 800, 1500))
    ]

    extra_row = [
        InlineKeyboardButton(text="📋 Шаблони", callback_data="choose_template"),
        InlineKeyboardButton(text="✏️ Інша", callback_data="manual_distance"),
    ]

    return InlineKeyboardMarkup(inline_keyboard=distance_buttons + [extra_row])


def get_template_keyboard(templates: Iterable[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Build keyboard with template choices."""

    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for template_id, title in templates:
        row.append(
            InlineKeyboardButton(
                text=title, callback_data=TemplateCB(template_id=template_id).pack()
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append(
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_distance"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_repeat_keyboard(athlete_id: int) -> InlineKeyboardMarkup:
    """Return keyboard with repeat action."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔁 Повторити попередній результат",
                    callback_data=RepeatCB(athlete_id=athlete_id).pack(),
                )
            ]
        ]
    )


def pack_timestamp_for_callback(timestamp: str) -> str:
    """Convert timestamp to callback-friendly format."""

    return timestamp.replace(" ", "_")


def unpack_timestamp_from_callback(raw: str) -> str:
    """Restore original timestamp from callback data."""

    return raw.replace("_", " ")


def get_comment_prompt_keyboard() -> InlineKeyboardMarkup:
    """Keyboard offering to skip comment input."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустити", callback_data="comment_skip")]
        ]
    )


def get_result_actions_keyboard(
    athlete_id: int, timestamp: str, has_comment: bool
) -> InlineKeyboardMarkup:
    """Keyboard with comment management and repeat actions."""

    packed_ts = pack_timestamp_for_callback(timestamp)
    comment_text = "✏️ Редагувати нотатку" if has_comment else "📝 Додати нотатку"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=comment_text,
                    callback_data=CommentCB(
                        action="edit", ts=packed_ts, athlete_id=athlete_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Повторити попередній результат",
                    callback_data=RepeatCB(athlete_id=athlete_id).pack(),
                )
            ],
        ]
    )


def get_main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Return main menu keyboard with optional admin buttons."""
    buttons = [
        [InlineKeyboardButton(text="Спринт", callback_data="menu_sprint")],
        [InlineKeyboardButton(text="Стаєр", callback_data="menu_stayer")],
        [InlineKeyboardButton(text="Історія", callback_data="menu_history")],
        [InlineKeyboardButton(text="Рекорди", callback_data="menu_records")],
    ]
    if is_admin:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="➕ Запросити спортсмена", callback_data="invite"
                )
            ]
        )
        buttons.append([InlineKeyboardButton(text="Адмін", callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
