from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Iterable, List, Tuple
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup

from handlers.add_wizard import (
    _format_summary,
    choose_distance,
    choose_style,
    choose_template,
    input_splits,
    input_total,
    start_wizard,
)
from i18n import reset_context_language, set_context_language, t
from keyboards import AddWizardCB


class DummyMessage:
    def __init__(self, text: str = "", user_id: int = 42, chat_id: int = 24) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(id=chat_id)
        self.answer = AsyncMock()


class DummyCallback:
    def __init__(self, message: DummyMessage) -> None:
        self.message = message
        self.from_user = message.from_user
        self.data = ""
        self.answer = AsyncMock()


def _make_state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=24, user_id=42)
    return FSMContext(storage=storage, key=key)


def _button_texts(markup: InlineKeyboardMarkup | None) -> List[str]:
    if markup is None:
        return []
    texts: List[str] = []
    for row in markup.inline_keyboard:
        texts.extend(button.text for button in row)
    return texts


def _capture_message(message: DummyMessage) -> Tuple[str, List[str]]:
    args, kwargs = message.answer.await_args
    text = args[0] if args else kwargs.get("text", "")
    markup = kwargs.get("reply_markup")
    buttons = _button_texts(
        markup if isinstance(markup, InlineKeyboardMarkup) else None
    )
    return text, buttons


async def _run_happy_path(lang: str) -> Tuple[List[Tuple[str, List[str]]], dict]:
    token = set_context_language(lang)
    try:
        state = _make_state()

        start_msg = DummyMessage()
        await start_wizard(start_msg, state)
        steps: List[Tuple[str, List[str]]] = [_capture_message(start_msg)]

        style_msg = DummyMessage()
        await choose_style(
            DummyCallback(style_msg),
            state,
            AddWizardCB(action="style", value="freestyle"),
        )
        steps.append(_capture_message(style_msg))

        style_msg.answer.reset_mock()
        await choose_distance(
            DummyCallback(style_msg), state, AddWizardCB(action="distance", value="100")
        )
        steps.append(_capture_message(style_msg))

        template_msg = DummyMessage()
        await choose_template(
            DummyCallback(template_msg),
            state,
            AddWizardCB(action="template", value="25.0|25.0|25.0|25.0"),
        )
        steps.append(_capture_message(template_msg))

        splits_msg = DummyMessage("0:30 0:31 0:32 0:30")
        await input_splits(splits_msg, state)
        steps.append(_capture_message(splits_msg))

        total_msg = DummyMessage("2:03")
        await input_total(total_msg, state)
        steps.append(_capture_message(total_msg))

        data = await state.get_data()
        return steps, data
    finally:
        reset_context_language(token)


def _assert_step_texts(lang: str) -> None:
    async def scenario() -> None:
        steps, data = await _run_happy_path(lang)

        token = set_context_language(lang)
        try:
            expected_texts = [
                t("add.step.style"),
                t("add.step.distance"),
                t("add.step.template", distance=100),
                t("add.step.splits"),
                t("add.step.total"),
                f"{t('add.step.confirm')}\n\n{_format_summary(data)}",
            ]
            expected_buttons = [
                [t("common.cancel")],
                [t("common.back"), t("common.cancel")],
                [t("common.back"), t("common.cancel")],
                [t("add.btn.autosum"), t("common.back"), t("common.cancel")],
                [t("add.btn.distribute"), t("common.back"), t("common.cancel")],
                [t("common.save"), t("common.back"), t("common.cancel")],
            ]
        finally:
            reset_context_language(token)

        for (text, buttons), expected_text, expected_btns in zip(
            steps, expected_texts, expected_buttons
        ):
            assert text == expected_text
            for button in expected_btns:
                assert button in buttons

    asyncio.run(scenario())


def test_add_wizard_i18n_uk() -> None:
    _assert_step_texts("uk")


def test_add_wizard_i18n_ru() -> None:
    _assert_step_texts("ru")
