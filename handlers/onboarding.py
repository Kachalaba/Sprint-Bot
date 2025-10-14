"""FSM onboarding flow for new users."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from handlers.menu import build_menu_keyboard
from handlers.registration import consume_invite, resolve_invite
from i18n import reset_context_language, set_context_language, t
from keyboards import (
    OnboardingLanguageCB,
    OnboardingRoleCB,
    get_onboarding_language_keyboard,
    get_onboarding_privacy_keyboard,
    get_onboarding_role_keyboard,
    get_onboarding_skip_keyboard,
)
from role_service import ROLE_ATHLETE, ROLE_TRAINER, RoleService
from services import get_athletes_worksheet
from services.user_service import UserProfile, UserService

logger = logging.getLogger(__name__)

router = Router()

_NAME_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁёІіЇїЄєҐґ0-9'’`\-\.\s]+$")
_MIN_NAME_LENGTH = 2
_MAX_NAME_LENGTH = 64

_LANGUAGE_KEYS = {"uk": "onb.languages.uk", "ru": "onb.languages.ru"}
_ROLE_KEYS = {ROLE_TRAINER: "onb.roles.trainer", ROLE_ATHLETE: "onb.roles.athlete"}

_PRIVACY_ACCEPT = "onboard_privacy_accept"
_PRIVACY_DECLINE = "onboard_privacy_decline"
_SKIP_GROUP = "onboard_skip_group"
_SKIP_TRAINER = "onboard_skip_trainer"
_SKIP_WORDS = {"пропустить", "skip", "-"}


class Onboarding(StatesGroup):
    """FSM states for onboarding."""

    choosing_role = State()
    confirming_privacy = State()
    entering_name = State()
    linking_trainer = State()
    entering_group = State()
    choosing_language = State()


def _clean_text(raw: str) -> str:
    return " ".join(raw.split())


def _validate_name(value: str) -> Optional[str]:
    """Return cleaned name if valid, otherwise ``None``."""

    cleaned = _clean_text(value)
    if not (_MIN_NAME_LENGTH <= len(cleaned) <= _MAX_NAME_LENGTH):
        return None
    if not _NAME_PATTERN.match(cleaned):
        return None
    return cleaned


def _translate_or_default(key: str | None, default: str) -> str:
    if not key:
        return default
    try:
        return t(key)
    except KeyError:
        return default


def _format_profile(profile: UserProfile) -> str:
    profile_language = profile.language or "uk"
    translation_language = (
        profile_language if profile_language in _LANGUAGE_KEYS else "uk"
    )
    token = set_context_language(translation_language)
    try:
        role_label = _translate_or_default(
            _ROLE_KEYS.get(profile.role), profile.role.title()
        )
        language_label = _translate_or_default(
            _LANGUAGE_KEYS.get(profile_language), profile_language
        )
        group_line = profile.group_name or "—"
        template = t("onb.profile_card")
        return template.format(
            name=profile.full_name,
            role=role_label,
            group=group_line,
            lang=language_label,
        )
    finally:
        reset_context_language(token)


def _preload_trainer_from_command(
    command: CommandStart.CommandObject | None,
) -> tuple[int | None, str | None, bool]:
    """Return trainer binding extracted from /start payload."""

    if command is None:
        return None, None, False
    payload = (command.args or "").strip()
    if not payload:
        return None, None, False

    invite = resolve_invite(payload)
    if invite:
        return invite.trainer_id, invite.code, False

    token = payload.split()[0]
    if token.startswith("+"):
        token = token[1:]
    if token.isdigit():
        return int(token), None, False
    return None, None, True


async def _trainer_label(role_service: RoleService, trainer_id: int) -> str:
    """Return readable label for trainer id using stored profiles."""

    try:
        trainers = await role_service.list_users(roles=(ROLE_TRAINER,))
    except Exception:  # pragma: no cover - defensive logging
        logger.debug(
            "Unable to fetch trainer list for label", exc_info=True
        )
        return str(trainer_id)
    for trainer in trainers:
        if trainer.telegram_id == trainer_id:
            return trainer.full_name or str(trainer_id)
    return str(trainer_id)


async def _append_athlete_row(user_id: int, name: str) -> None:
    """Append athlete to Google Sheet using background thread."""

    try:
        worksheet = get_athletes_worksheet()
    except RuntimeError as exc:  # pragma: no cover - external dependency
        logger.warning("Failed to access athletes worksheet: %s", exc)
        return

    timestamp = datetime.now(timezone.utc).isoformat(" ", "seconds")
    try:
        await asyncio.to_thread(
            worksheet.append_row,
            [user_id, name, timestamp],
        )
    except Exception as exc:  # pragma: no cover - external dependency
        logger.warning(
            "Failed to append athlete %s to worksheet: %s", user_id, exc
        )


async def _proceed_to_group(state: FSMContext, message: Message) -> None:
    await state.set_state(Onboarding.entering_group)
    await message.answer(
        t("onb.group_hint"), reply_markup=get_onboarding_skip_keyboard("group")
    )


def _parse_trainer_reference(value: str) -> tuple[int | None, str | None]:
    """Parse trainer reference from user input."""

    cleaned = value.strip()
    if not cleaned:
        return None, None
    invite = resolve_invite(cleaned)
    if invite:
        return invite.trainer_id, invite.code
    token = cleaned.split()[0]
    if token.startswith("+"):
        token = token[1:]
    if token.isdigit():
        return int(token), None
    return None, None


async def _link_trainer(
    role_service: RoleService, athlete_id: int, trainer_id: int
) -> bool:
    """Persist trainer linkage for athlete and return success flag."""

    try:
        await role_service.set_trainer(athlete_id, trainer_id)
    except Exception:  # pragma: no cover - relies on DB state
        logger.warning(
            "Failed to link athlete %s with trainer %s",
            athlete_id,
            trainer_id,
            exc_info=True,
        )
        return False
    return True


async def _finalise_trainer_link(
    role_service: RoleService,
    user_id: int,
    data: dict[str, object],
    *,
    full_name: str | None,
) -> str | None:
    """Link trainer if provided and return status message."""

    trainer_raw = data.get("trainer_id")
    invite_code = data.get("invite_code")
    if not trainer_raw:
        if isinstance(invite_code, str):
            consume_invite(invite_code)
        return None

    try:
        trainer_id = int(trainer_raw)
    except (TypeError, ValueError):
        if isinstance(invite_code, str):
            consume_invite(invite_code)
        return t("onb.trainer_link_failed")

    linked = await _link_trainer(role_service, user_id, trainer_id)
    if not linked:
        if isinstance(invite_code, str):
            consume_invite(invite_code)
        return t("onb.trainer_link_failed")

    if isinstance(invite_code, str):
        consume_invite(invite_code)
        if full_name:
            await _append_athlete_row(user_id, full_name)

    label = await _trainer_label(role_service, trainer_id)
    return t("onb.trainer_linked").format(trainer=label)


@router.message(CommandStart())
async def start_onboarding(
    message: Message,
    state: FSMContext,
    user_service: UserService,
    role_service: RoleService,
    command: CommandStart.CommandObject | None = None,
) -> None:
    """Handle /start: run onboarding or show profile."""

    await state.clear()
    user_id = message.from_user.id
    trainer_id, invite_code, invalid_payload = _preload_trainer_from_command(command)

    profile = await user_service.get_profile(user_id)
    if profile:
        await role_service.set_role(user_id, profile.role)
        if trainer_id and profile.role == ROLE_ATHLETE:
            if await _link_trainer(role_service, user_id, trainer_id):
                if invite_code:
                    consume_invite(invite_code)
                label = await _trainer_label(role_service, trainer_id)
                await message.answer(
                    t("onb.trainer_linked_existing").format(trainer=label)
                )
            else:
                await message.answer(t("onb.trainer_link_failed"))
        elif invalid_payload:
            await message.answer(t("onb.invite_invalid"))
        await message.answer(
            _format_profile(profile), reply_markup=build_menu_keyboard(profile.role)
        )
        return

    payload: dict[str, object] = {}
    if trainer_id:
        payload["trainer_id"] = trainer_id
    if invite_code:
        payload["invite_code"] = invite_code
    if payload:
        await state.update_data(**payload)
        label = await _trainer_label(role_service, trainer_id) if trainer_id else None
        if label:
            await message.answer(
                t("onb.trainer_pending").format(trainer=label)
            )
    elif invalid_payload:
        await message.answer(t("onb.invite_invalid"))

    await state.set_state(Onboarding.choosing_role)
    await message.answer(
        t("onb.choose_role"), reply_markup=get_onboarding_role_keyboard()
    )


@router.callback_query(Onboarding.choosing_role, OnboardingRoleCB.filter())
async def process_role(
    callback: CallbackQuery,
    callback_data: OnboardingRoleCB,
    state: FSMContext,
) -> None:
    """Save chosen role and ask for privacy confirmation."""

    role = callback_data.role
    await state.update_data(role=role)
    await state.set_state(Onboarding.confirming_privacy)
    await callback.message.edit_reply_markup()
    role_label = _translate_or_default(_ROLE_KEYS.get(role), role.title())
    await callback.message.answer(
        t("onb.privacy_notice").format(role=role_label),
        reply_markup=get_onboarding_privacy_keyboard(),
    )
    await callback.answer()


@router.callback_query(Onboarding.confirming_privacy, F.data == _PRIVACY_ACCEPT)
async def accept_privacy(callback: CallbackQuery, state: FSMContext) -> None:
    """Continue onboarding after privacy confirmation."""

    await state.set_state(Onboarding.entering_name)
    await callback.message.edit_reply_markup()
    await callback.message.answer(t("onb.enter_name"))
    await callback.answer(t("onb.privacy_ack"))


@router.callback_query(Onboarding.confirming_privacy, F.data == _PRIVACY_DECLINE)
async def decline_privacy(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel onboarding when user declines privacy statement."""

    data = await state.get_data()
    consume_invite(data.get("invite_code"))
    await state.clear()
    await callback.message.edit_reply_markup()
    await callback.message.answer(t("onb.privacy_declined"))
    await callback.answer()


@router.message(Onboarding.entering_name, F.text)
async def process_name(message: Message, state: FSMContext) -> None:
    """Validate and store user name."""

    name = message.text or ""
    cleaned = _validate_name(name)
    if not cleaned:
        await message.answer(t("error.name_invalid"))
        return
    await state.update_data(full_name=cleaned)
    await message.answer(t("user.step_saved"))

    data = await state.get_data()
    role = data.get("role", ROLE_ATHLETE)
    if role == ROLE_ATHLETE and not data.get("trainer_id"):
        await state.set_state(Onboarding.linking_trainer)
        await message.answer(
            t("onb.trainer_hint"),
            reply_markup=get_onboarding_skip_keyboard("trainer"),
        )
        return

    await _proceed_to_group(state, message)


@router.message(Onboarding.linking_trainer, F.text)
async def process_trainer(
    message: Message,
    state: FSMContext,
    role_service: RoleService,
) -> None:
    """Handle trainer linkage input."""

    text = message.text or ""
    if text.casefold() in _SKIP_WORDS:
        await state.update_data(trainer_id=None, invite_code=None)
        await message.answer(t("user.step_skipped"))
        await _proceed_to_group(state, message)
        return

    trainer_id, invite_code = _parse_trainer_reference(text)
    if not trainer_id:
        await message.answer(t("onb.trainer_invalid"))
        return

    await state.update_data(trainer_id=trainer_id, invite_code=invite_code)
    label = await _trainer_label(role_service, trainer_id)
    await message.answer(t("onb.trainer_saved").format(trainer=label))
    await _proceed_to_group(state, message)


@router.callback_query(Onboarding.linking_trainer, F.data == _SKIP_TRAINER)
async def skip_trainer_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle inline skip for trainer step."""

    await state.update_data(trainer_id=None, invite_code=None)
    await callback.message.edit_reply_markup()
    await callback.answer(t("user.step_skipped"))
    await _proceed_to_group(state, callback.message)


@router.message(Onboarding.entering_group, F.text)
async def process_group(message: Message, state: FSMContext) -> None:
    """Store provided group or skip if requested."""

    text = message.text or ""
    if text.casefold() in _SKIP_WORDS:
        await state.update_data(group_name=None)
    else:
        cleaned = text.strip()
        if cleaned:
            await state.update_data(group_name=cleaned[:80])
        else:
            await state.update_data(group_name=None)
    await message.answer(t("user.step_saved"))
    await _proceed_to_language(state, message)


async def _proceed_to_language(state: FSMContext, message: Message) -> None:
    await state.set_state(Onboarding.choosing_language)
    await message.answer(
        t("onb.choose_lang"), reply_markup=get_onboarding_language_keyboard()
    )


@router.callback_query(Onboarding.entering_group, F.data == _SKIP_GROUP)
async def skip_group_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle inline skip for group step."""

    await state.update_data(group_name=None)
    await callback.message.edit_reply_markup()
    await callback.answer(t("user.step_skipped"))
    await _proceed_to_language(state, callback.message)


@router.callback_query(Onboarding.choosing_language, OnboardingLanguageCB.filter())
async def process_language(
    callback: CallbackQuery,
    callback_data: OnboardingLanguageCB,
    state: FSMContext,
    user_service: UserService,
    role_service: RoleService,
) -> None:
    """Persist profile and finish onboarding."""

    language = callback_data.language
    data = await state.get_data()
    role = data.get("role", ROLE_ATHLETE)
    full_name = data.get("full_name")
    group_name = data.get("group_name")
    user_id = callback.from_user.id

    if not full_name:
        logger.warning("Missing name in onboarding state for %s", user_id)
        consume_invite(data.get("invite_code"))
        await callback.answer(t("user.onboarding_restart"), show_alert=True)
        await state.clear()
        return

    await user_service.upsert_profile(
        user_id,
        role=role,
        full_name=full_name,
        language=language,
        group_name=group_name,
    )
    await role_service.set_role(user_id, role)

    trainer_message: str | None = None
    if role == ROLE_ATHLETE:
        trainer_message = await _finalise_trainer_link(
            role_service,
            user_id,
            data,
            full_name=full_name,
        )
    else:
        invite_code = data.get("invite_code")
        if isinstance(invite_code, str):
            consume_invite(invite_code)

    profile = await user_service.get_profile(user_id)
    await state.clear()
    await callback.message.edit_reply_markup()
    if profile:
        await callback.message.answer(
            _format_profile(profile), reply_markup=build_menu_keyboard(profile.role)
        )
    else:
        await callback.message.answer(
            t("user.profile_saved"), reply_markup=build_menu_keyboard(role)
        )
    if trainer_message:
        await callback.message.answer(trainer_message)
    await callback.answer(t("user.language_changed"))
