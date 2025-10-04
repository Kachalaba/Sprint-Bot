from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from handlers.add_wizard import (
    AddWizardStates,
    _encode_template_payload,
    _generate_segment_templates,
    choose_distance,
    choose_style,
    choose_template,
    input_splits,
    input_turn_details,
    start_wizard,
)
from i18n import t
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


def test_turn_state_triggered_for_breaststroke_template() -> None:
    async def scenario() -> None:
        state = _make_state()
        start_msg = DummyMessage()
        await start_wizard(start_msg, state)

        style_cb = DummyCallback(start_msg)
        await choose_style(
            style_cb,
            state,
            AddWizardCB(action="style", value="STROKE_BREASTSTROKE"),
        )

        distance_cb = DummyCallback(start_msg)
        await choose_distance(
            distance_cb,
            state,
            AddWizardCB(action="distance", value="100"),
        )

        templates = _generate_segment_templates(100, "breaststroke")
        turn_template = templates[0]
        payload = _encode_template_payload(turn_template)

        template_cb = DummyCallback(start_msg)
        await choose_template(
            template_cb,
            state,
            AddWizardCB(action="template", value=payload),
        )
        assert await state.get_state() == AddWizardStates.enter_splits.state

        splits_msg = DummyMessage("0:30 0:31 0:30 0:32")
        await input_splits(splits_msg, state)
        assert await state.get_state() == AddWizardStates.enter_turn_details.state
        prompt = splits_msg.answer.await_args[0][0]
        expected_prompt = t("add.step.turns", count=3)
        assert prompt == expected_prompt

    asyncio.run(scenario())


def test_turn_templates_include_turn_labels() -> None:
    async def scenario() -> None:
        templates = _generate_segment_templates(100, "butterfly")
        assert templates[0].segment_types.count("turn") == 3

        freestyle_templates = _generate_segment_templates(100, "freestyle")
        assert freestyle_templates[0].segment_types.count("turn") == 0

    asyncio.run(scenario())


def test_input_turn_details_validation_flow() -> None:
    async def scenario() -> None:
        state = _make_state()
        await state.update_data(
            style="butterfly",
            segment_types=("swim", "turn", "swim", "turn"),
        )
        await state.set_state(AddWizardStates.enter_turn_details)

        bad_format_msg = DummyMessage("oops")
        await input_turn_details(bad_format_msg, state)
        assert bad_format_msg.answer.await_args[0][0] == t("error.invalid_time")

        mismatch_msg = DummyMessage("0:03")
        await input_turn_details(mismatch_msg, state)
        assert await state.get_state() == AddWizardStates.enter_turn_details.state

        valid_msg = DummyMessage("0:03 0:04")
        await input_turn_details(valid_msg, state)
        assert await state.get_state() == AddWizardStates.enter_total.state
        total_prompt = valid_msg.answer.await_args[0][0]
        assert total_prompt == t("add.step.total")

    asyncio.run(scenario())
