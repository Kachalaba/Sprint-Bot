from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram import Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from handlers.menu import build_menu_keyboard, cmd_menu, menu_progress_redirect, router
from i18n import reset_context_language, set_context_language, t
from menu_callbacks import CB_MENU_PROGRESS
from role_service import ROLE_ATHLETE


def _button_label(markup: InlineKeyboardMarkup, callback_data: str) -> str:
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data == callback_data:
                return button.text
    raise AssertionError(f"No button with callback data '{callback_data}' found")


def test_menu_progress_callback_uses_callback_data() -> None:
    token_ru = set_context_language("ru")
    try:
        keyboard_ru = build_menu_keyboard(ROLE_ATHLETE)
        ru_label = _button_label(keyboard_ru, CB_MENU_PROGRESS)
    finally:
        reset_context_language(token_ru)

    token_uk = set_context_language("uk")
    try:
        keyboard_uk = build_menu_keyboard(ROLE_ATHLETE)
        uk_label = _button_label(keyboard_uk, CB_MENU_PROGRESS)
    finally:
        reset_context_language(token_uk)

    assert ru_label != uk_label

    handler = next(
        handler
        for handler in router.callback_query.handlers
        if handler.callback is menu_progress_redirect
    )

    base_event = {
        "id": "1",
        "from": {"id": 1, "is_bot": False, "first_name": "Test"},
        "message": {
            "message_id": 1,
            "date": datetime.now(),
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 1, "is_bot": False, "first_name": "Test"},
            "text": "",
        },
        "chat_instance": "instance",
    }

    success_event = CallbackQuery.model_validate(
        base_event | {"data": CB_MENU_PROGRESS}
    )
    failed_event = CallbackQuery.model_validate(base_event | {"data": ru_label})

    async def scenario() -> None:
        passed, _ = await handler.check(success_event)
        assert passed

        passed_with_label, _ = await handler.check(failed_event)
        assert not passed_with_label

    asyncio.run(scenario())


def test_menu_command_is_triggered_by_slash_command() -> None:
    handler = next(
        handler for handler in router.message.handlers if handler.callback is cmd_menu
    )

    message_command = Message.model_validate(
        {
            "message_id": 1,
            "date": datetime.now(),
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 1, "is_bot": False, "first_name": "Tester"},
            "text": "/menu",
            "entities": [{"type": "bot_command", "offset": 0, "length": 5}],
        }
    )

    localized_text = t("menu.title", lang="ru")
    message_localized = message_command.model_copy(
        update={"text": localized_text, "entities": []}
    )

    async def scenario() -> None:
        bot = Bot(token="42:TEST", parse_mode=None)
        try:
            passed, _ = await handler.check(message_command, bot=bot)
            assert passed

            passed_with_translation, _ = await handler.check(message_localized, bot=bot)
            assert not passed_with_translation
        finally:
            await bot.session.close()

    asyncio.run(scenario())
