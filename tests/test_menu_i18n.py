from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from handlers.menu import build_menu_keyboard
from i18n import reset_context_language, set_context_language, t
from menu_callbacks import (
    CB_MENU_ADD_RESULT,
    CB_MENU_PROGRESS,
    CB_MENU_REPORTS,
    CB_MENU_TEMPLATES,
)
from role_service import ROLE_ATHLETE, ROLE_TRAINER


def _button_label(markup: InlineKeyboardMarkup, callback_data: str) -> str:
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data == callback_data:
                return button.text
    raise AssertionError(f"Button {callback_data} not found")


def test_menu_keyboard_translations_ru() -> None:
    token = set_context_language("ru")
    try:
        keyboard = build_menu_keyboard(ROLE_TRAINER)
        assert _button_label(keyboard, CB_MENU_ADD_RESULT) == t(
            "menu.buttons.add_result"
        )
        assert _button_label(keyboard, CB_MENU_TEMPLATES) == t("menu.buttons.templates")
        assert _button_label(keyboard, CB_MENU_REPORTS) == t("menu.buttons.reports")
    finally:
        reset_context_language(token)


def test_menu_keyboard_translations_uk() -> None:
    token = set_context_language("uk")
    try:
        keyboard = build_menu_keyboard(ROLE_ATHLETE)
        assert _button_label(keyboard, CB_MENU_PROGRESS) == t(
            "menu.buttons.my_progress"
        )
    finally:
        reset_context_language(token)
