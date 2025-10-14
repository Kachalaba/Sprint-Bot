import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Awaitable, Callable
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from handlers import onboarding as onboarding_module
from handlers.onboarding import (
    Onboarding,
    accept_privacy,
    decline_privacy,
    process_group,
    process_language,
    process_name,
    process_role,
    skip_trainer_callback,
    start_onboarding,
)
from handlers.registration import active_invites
from i18n import t
from keyboards import OnboardingLanguageCB, OnboardingRoleCB
from role_service import ROLE_TRAINER, RoleService
from services.user_service import UserService

_DEFAULT_USER_ID = 100
_DEFAULT_CHAT_ID = 200


class DummyMessage:
    def __init__(
        self,
        text: str = "",
        *,
        user_id: int = _DEFAULT_USER_ID,
        chat_id: int = _DEFAULT_CHAT_ID,
        full_name: str = "Test User",
    ) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=user_id, full_name=full_name)
        self.chat = SimpleNamespace(id=chat_id)
        self.answer = AsyncMock()
        self.edit_reply_markup = AsyncMock()


class DummyCallback:
    def __init__(
        self,
        message: DummyMessage,
        *,
        data: str | None = None,
    ) -> None:
        self.message = message
        self.from_user = message.from_user
        self.data = data
        self.answer = AsyncMock()


SetupHook = Callable[[UserService, RoleService], Awaitable[None]]


@dataclass(slots=True)
class OnboardingScenario:
    state: FSMContext
    user_service: UserService
    role_service: RoleService
    start_message: DummyMessage

    @classmethod
    async def start(
        cls,
        tmp_path,
        *,
        payload: str | None = None,
        setup: SetupHook | None = None,
        user_id: int = _DEFAULT_USER_ID,
        chat_id: int = _DEFAULT_CHAT_ID,
    ) -> "OnboardingScenario":
        storage = MemoryStorage()
        state = FSMContext(
            storage=storage,
            key=StorageKey(bot_id=1, chat_id=chat_id, user_id=user_id),
        )
        user_service = UserService(tmp_path / "users.db")
        role_service = RoleService(tmp_path / "roles.db")
        await user_service.init()
        await role_service.init()
        if setup is not None:
            await setup(user_service, role_service)
        start_msg = DummyMessage(user_id=user_id, chat_id=chat_id)
        command = SimpleNamespace(args=payload)
        await start_onboarding(
            start_msg,
            state,
            user_service,
            role_service,
            command=command,
        )
        return cls(
            state=state,
            user_service=user_service,
            role_service=role_service,
            start_message=start_msg,
        )

    def new_message(
        self, text: str = "", *, full_name: str | None = None
    ) -> DummyMessage:
        return DummyMessage(
            text,
            user_id=self.start_message.from_user.id,
            chat_id=self.start_message.chat.id,
            full_name=full_name or self.start_message.from_user.full_name,
        )

    @staticmethod
    def new_callback(
        message: DummyMessage, *, data: str | None = None
    ) -> DummyCallback:
        return DummyCallback(message, data=data)


def _last_answer_text(message: DummyMessage) -> str:
    if not message.answer.await_args_list:
        raise AssertionError("message.answer was not awaited")
    return message.answer.await_args_list[-1].args[0]


def test_onboarding_happy_path(tmp_path) -> None:
    async def scenario() -> None:
        active_invites.clear()
        context = await OnboardingScenario.start(tmp_path)

        state = await context.state.get_state()
        assert state == Onboarding.choosing_role.state
        start_answers = context.start_message.answer.await_args_list
        prompts = [call.args[0] for call in start_answers]
        assert prompts[-1] == t("onb.choose_role")

        role_cb = context.new_callback(context.start_message)
        await process_role(
            role_cb,
            OnboardingRoleCB(role="athlete"),
            context.state,
        )
        state = await context.state.get_state()
        assert state == Onboarding.confirming_privacy.state
        role_cb.message.edit_reply_markup.assert_awaited()
        role_cb.answer.assert_awaited()

        privacy_message = context.new_message()
        privacy_cb = context.new_callback(privacy_message)
        await accept_privacy(privacy_cb, context.state)
        state = await context.state.get_state()
        assert state == Onboarding.entering_name.state
        privacy_cb.message.edit_reply_markup.assert_awaited()
        privacy_prompt = _last_answer_text(privacy_message)
        assert privacy_prompt == t("onb.enter_name")
        privacy_alert = privacy_cb.answer.await_args[0][0]
        assert privacy_alert == t("onb.privacy_ack")

        name_message = context.new_message("Test Athlete")
        await process_name(name_message, context.state)
        state = await context.state.get_state()
        assert state == Onboarding.linking_trainer.state
        name_answers = name_message.answer.await_args_list
        saved_texts = [call.args[0] for call in name_answers]
        assert t("user.step_saved") in saved_texts
        assert t("onb.trainer_hint") in saved_texts

        skip_cb = context.new_callback(name_message)
        await skip_trainer_callback(skip_cb, context.state)
        state = await context.state.get_state()
        assert state == Onboarding.entering_group.state
        skip_cb.message.edit_reply_markup.assert_awaited()
        skip_alert = skip_cb.answer.await_args[0][0]
        assert skip_alert == t("user.step_skipped")

        group_message = context.new_message("Wave")
        await process_group(group_message, context.state)
        state = await context.state.get_state()
        assert state == Onboarding.choosing_language.state
        group_answers = group_message.answer.await_args_list
        group_texts = [call.args[0] for call in group_answers]
        assert t("user.step_saved") in group_texts
        assert t("onb.choose_lang") in group_texts

        lang_cb = context.new_callback(group_message)
        await process_language(
            lang_cb,
            OnboardingLanguageCB(language="uk"),
            context.state,
            context.user_service,
            context.role_service,
        )
        assert await context.state.get_state() is None
        lang_cb.message.edit_reply_markup.assert_awaited()
        language_alert = lang_cb.answer.await_args[0][0]
        assert language_alert == t("user.language_changed")
        profile_answers = group_message.answer.await_args_list
        profile_texts = [call.args[0] for call in profile_answers]
        assert any("Test Athlete" in text for text in profile_texts)

        profile = await context.user_service.get_profile(
            context.start_message.from_user.id
        )
        assert profile is not None
        assert profile.full_name == "Test Athlete"
        assert profile.group_name == "Wave"
        assert profile.language == "uk"

    asyncio.run(scenario())


def test_onboarding_privacy_decline_clears_state(tmp_path) -> None:
    async def scenario() -> None:
        active_invites.clear()
        active_invites["abc123"] = 555

        context = await OnboardingScenario.start(
            tmp_path,
            payload="\u0440\u0435\u0433_abc123",
        )
        state = await context.state.get_state()
        assert state == Onboarding.choosing_role.state

        role_cb = context.new_callback(context.start_message)
        await process_role(
            role_cb,
            OnboardingRoleCB(role="athlete"),
            context.state,
        )
        state = await context.state.get_state()
        assert state == Onboarding.confirming_privacy.state

        decline_message = context.new_message()
        decline_cb = context.new_callback(decline_message)
        await decline_privacy(decline_cb, context.state)

        assert await context.state.get_state() is None
        assert not active_invites
        decline_cb.message.edit_reply_markup.assert_awaited()
        decline_text = _last_answer_text(decline_message)
        assert decline_text == t("onb.privacy_declined")

    asyncio.run(scenario())


def test_onboarding_invite_links_trainer(tmp_path) -> None:
    async def scenario() -> None:
        active_invites.clear()
        trainer_id = 555
        active_invites["abc123"] = trainer_id

        appended_rows: list[tuple[object, ...]] = []

        class FakeWorksheet:
            def append_row(self, row: list[object]) -> None:
                appended_rows.append(tuple(row))

        original_get_sheet = onboarding_module.get_athletes_worksheet
        fake_sheet = FakeWorksheet()
        onboarding_module.get_athletes_worksheet = lambda: fake_sheet

        async def setup(
            _user_service: UserService,
            role_service: RoleService,
        ) -> None:
            await role_service.upsert_user(
                SimpleNamespace(id=trainer_id, full_name="Coach Fox"),
                default_role=ROLE_TRAINER,
            )

        try:
            context = await OnboardingScenario.start(
                tmp_path,
                payload="reg_abc123",
                setup=setup,
            )

            start_answers = context.start_message.answer.await_args_list
            prompts = [call.args[0] for call in start_answers]
            pending_template = t("onb.trainer_pending")
            pending_label = pending_template.format(trainer="Coach Fox")
            assert pending_label in prompts[0]
            assert prompts[-1] == t("onb.choose_role")

            role_cb = context.new_callback(context.start_message)
            await process_role(
                role_cb,
                OnboardingRoleCB(role="athlete"),
                context.state,
            )
            state = await context.state.get_state()
            assert state == Onboarding.confirming_privacy.state

            privacy_message = context.new_message()
            privacy_cb = context.new_callback(privacy_message)
            await accept_privacy(privacy_cb, context.state)
            state = await context.state.get_state()
            assert state == Onboarding.entering_name.state

            name_message = context.new_message("Alice Runner")
            await process_name(name_message, context.state)
            state = await context.state.get_state()
            assert state == Onboarding.entering_group.state

            group_message = context.new_message("Wave A")
            await process_group(group_message, context.state)
            state = await context.state.get_state()
            assert state == Onboarding.choosing_language.state

            lang_cb = context.new_callback(group_message)
            await process_language(
                lang_cb,
                OnboardingLanguageCB(language="ru"),
                context.state,
                context.user_service,
                context.role_service,
            )
            assert await context.state.get_state() is None
            language_alert = lang_cb.answer.await_args[0][0]
            assert language_alert == t("user.language_changed")

            profile = await context.user_service.get_profile(
                context.start_message.from_user.id
            )
            assert profile is not None
            assert profile.full_name == "Alice Runner"
            assert profile.group_name == "Wave A"
            assert profile.language == "ru"

            trainers = await context.role_service.trainers_for_athlete(
                context.start_message.from_user.id
            )
            assert trainers == (trainer_id,)
            assert not active_invites
            assert appended_rows
            last_row = appended_rows[-1]
            assert last_row[0] == context.start_message.from_user.id
            assert last_row[1] == "Alice Runner"
        finally:
            onboarding_module.get_athletes_worksheet = original_get_sheet

    asyncio.run(scenario())
