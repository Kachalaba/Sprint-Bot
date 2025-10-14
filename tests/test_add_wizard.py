from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from handlers.add_wizard import (
    AddWizardStates,
    autosum_splits,
    cancel_wizard,
    choose_distance,
    choose_style,
    choose_template,
    even_from_total,
    input_splits,
    input_total,
    navigate_back,
    save_result,
    start_wizard,
)
from keyboards import AddWizardCB
from i18n import t


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


def test_wizard_happy_path() -> None:
    async def scenario() -> None:
        state = _make_state()
        start_msg = DummyMessage()
        await start_wizard(start_msg, state)
        assert await state.get_state() == AddWizardStates.choose_style.state
        start_msg.answer.assert_called_once()

        style_msg = DummyMessage()
        style_cb = DummyCallback(style_msg)
        await choose_style(style_cb, state, AddWizardCB(action="style", value="freestyle"))
        assert await state.get_state() == AddWizardStates.choose_distance.state
        style_cb.answer.assert_awaited()
        style_msg.answer.assert_called_once()

        style_msg.answer.reset_mock()
        distance_cb = DummyCallback(style_msg)
        await choose_distance(distance_cb, state, AddWizardCB(action="distance", value="100"))
        assert await state.get_state() == AddWizardStates.choose_template.state
        distance_cb.answer.assert_awaited()
        style_msg.answer.assert_called_once()

        template_msg = DummyMessage()
        template_cb = DummyCallback(template_msg)
        await choose_template(
            template_cb,
            state,
            AddWizardCB(action="template", value="25.0|25.0|25.0|25.0"),
        )
        assert await state.get_state() == AddWizardStates.enter_splits.state
        template_msg.answer.assert_called_once()

        splits_msg = DummyMessage("0:30 0:31 0:32 0:30")
        await input_splits(splits_msg, state)
        assert await state.get_state() == AddWizardStates.enter_total.state
        splits_msg.answer.assert_called_once()

        total_msg = DummyMessage("2:03")
        await input_total(total_msg, state)
        assert await state.get_state() == AddWizardStates.confirm.state
        total_msg.answer.assert_called_once()
        summary_text = total_msg.answer.await_args[0][0]
        assert "Перевірка даних" in summary_text

        confirm_msg = DummyMessage()
        confirm_cb = DummyCallback(confirm_msg)
        await save_result(confirm_cb, state)
        assert await state.get_state() is None
        confirm_cb.answer.assert_awaited()
        confirm_msg.answer.assert_called_once()
        final_text = confirm_msg.answer.await_args[0][0]
        assert "Результат збережено" in final_text

    asyncio.run(scenario())


def test_wizard_split_correction() -> None:
    async def scenario() -> None:
        state = _make_state()
        await start_wizard(DummyMessage(), state)
        await choose_style(
            DummyCallback(DummyMessage()),
            state,
            AddWizardCB(action="style", value="freestyle"),
        )
        carrier = DummyMessage()
        await choose_distance(
            DummyCallback(carrier),
            state,
            AddWizardCB(action="distance", value="100"),
        )
        await choose_template(
            DummyCallback(carrier),
            state,
            AddWizardCB(action="template", value="25.0|25.0|25.0|25.0"),
        )

        bad_msg = DummyMessage("0:30 0:31")
        await input_splits(bad_msg, state)
        bad_msg.answer.assert_called_with(
            "Кількість сплітів не відповідає шаблону. Спробуйте ще раз."
        )
        assert await state.get_state() == AddWizardStates.enter_splits.state

        good_msg = DummyMessage("0:30 0:31 0:30 0:32")
        await input_splits(good_msg, state)
        assert await state.get_state() == AddWizardStates.enter_total.state

        carrier.answer.reset_mock()
        auto_cb = DummyCallback(carrier)
        await autosum_splits(auto_cb, state)
        carrier.answer.assert_called_once()
        message_text = carrier.answer.await_args[0][0]
        assert message_text.startswith("Сума сплітів")

        total_msg = DummyMessage("2:03")
        await input_total(total_msg, state)
        assert await state.get_state() == AddWizardStates.confirm.state

        back_cb = DummyCallback(carrier)
        await navigate_back(back_cb, state, AddWizardCB(action="back", value="total"))
        assert await state.get_state() == AddWizardStates.enter_total.state

        even_cb = DummyCallback(carrier)
        data = await state.get_data()
        await state.update_data(total=sum(data.get("splits", [])))
        carrier.answer.reset_mock()
        await even_from_total(even_cb, state)
        carrier.answer.assert_called_once()

    asyncio.run(scenario())


def test_wizard_cancel() -> None:
    async def scenario() -> None:
        state = _make_state()
        start_msg = DummyMessage()
        await start_wizard(start_msg, state)
        cancel_cb = DummyCallback(start_msg)
        await cancel_wizard(cancel_cb, state)
        assert await state.get_state() is None
        cancel_cb.answer.assert_awaited()
        start_msg.answer.assert_called_with(t("add.error.cancelled"))

    asyncio.run(scenario())


def test_wizard_cancel_command_from_user() -> None:
    async def scenario() -> None:
        state = _make_state()
        carrier = DummyMessage()
        await start_wizard(carrier, state)
        await choose_style(
            DummyCallback(carrier),
            state,
            AddWizardCB(action="style", value="freestyle"),
        )
        await choose_distance(
            DummyCallback(carrier), state, AddWizardCB(action="distance", value="100")
        )
        await choose_template(
            DummyCallback(carrier),
            state,
            AddWizardCB(action="template", value="25.0|25.0|25.0|25.0"),
        )

        cancel_msg = DummyMessage("/cancel")
        await input_splits(cancel_msg, state)
        assert await state.get_state() is None
        cancel_msg.answer.assert_awaited()
        assert cancel_msg.answer.await_args[0][0] == t("add.error.cancelled")

    asyncio.run(scenario())


def test_wizard_repeat_command_repeats_hint() -> None:
    async def scenario() -> None:
        state = _make_state()
        carrier = DummyMessage()
        await start_wizard(carrier, state)
        await choose_style(
            DummyCallback(carrier),
            state,
            AddWizardCB(action="style", value="freestyle"),
        )
        await choose_distance(
            DummyCallback(carrier), state, AddWizardCB(action="distance", value="100")
        )
        await choose_template(
            DummyCallback(carrier),
            state,
            AddWizardCB(action="template", value="25.0|25.0|25.0|25.0"),
        )

        repeat_msg = DummyMessage("/repeat")
        await input_splits(repeat_msg, state)
        assert await state.get_state() == AddWizardStates.enter_splits.state
        assert repeat_msg.answer.await_count == 2
        first_message = repeat_msg.answer.await_args_list[0][0][0]
        assert first_message == t("add.error.repeat")

    asyncio.run(scenario())
