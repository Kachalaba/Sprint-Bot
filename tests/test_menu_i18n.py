from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from handlers.menu import build_menu_keyboard
from i18n import reset_context_language, set_context_language, t
from role_service import ROLE_ATHLETE, ROLE_TRAINER


def _button_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_menu_keyboard_translations_ru() -> None:
    token = set_context_language("ru")
    try:
        keyboard = build_menu_keyboard(ROLE_TRAINER)
        expected = [
            t("menu.add_result"),
            t("menu.templates"),
            t("menu.reports"),
            t("menu.search_history"),
        ]
    finally:
        reset_context_language(token)
    assert _button_texts(keyboard) == expected


def test_menu_keyboard_translations_uk() -> None:
    token = set_context_language("uk")
    try:
        keyboard = build_menu_keyboard(ROLE_ATHLETE)
        expected = [
            t("menu.my_results"),
            t("menu.my_progress"),
        ]
    finally:
        reset_context_language(token)
    assert _button_texts(keyboard) == expected
