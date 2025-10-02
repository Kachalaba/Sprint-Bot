from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from i18n import reset_context_language, set_context_language
from keyboards import (
    build_main_reply_keyboard,
    get_distance_keyboard,
    get_main_keyboard,
)
from role_service import ROLE_TRAINER


def _inline_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _reply_texts(markup: ReplyKeyboardMarkup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


def test_keyboard_buttons_translate_between_languages() -> None:
    uk_token = set_context_language("uk")
    try:
        uk_reply = _reply_texts(build_main_reply_keyboard())
        uk_inline = _inline_texts(get_main_keyboard(ROLE_TRAINER))
        uk_distance = _inline_texts(get_distance_keyboard())
    finally:
        reset_context_language(uk_token)

    ru_token = set_context_language("ru")
    try:
        ru_reply = _reply_texts(build_main_reply_keyboard())
        ru_inline = _inline_texts(get_main_keyboard(ROLE_TRAINER))
        ru_distance = _inline_texts(get_distance_keyboard())
    finally:
        reset_context_language(ru_token)

    assert uk_reply != ru_reply
    assert uk_inline != ru_inline
    assert uk_distance != ru_distance
