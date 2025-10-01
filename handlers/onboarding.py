"""FSM onboarding flow for new users."""

from __future__ import annotations

import logging
import re
from typing import Optional

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from handlers.menu import build_menu_keyboard
from keyboards import (
    get_onboarding_language_keyboard,
    get_onboarding_role_keyboard,
    get_onboarding_skip_keyboard,
    OnboardingLanguageCB,
    OnboardingRoleCB,
)
from role_service import ROLE_ATHLETE, ROLE_TRAINER, RoleService
from services.user_service import UserProfile, UserService

logger = logging.getLogger(__name__)

router = Router()

_NAME_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁёІіЇїЄєҐґ0-9'’`\-\.\s]+$")
_MIN_NAME_LENGTH = 2
_MAX_NAME_LENGTH = 64

_LANGUAGE_LABELS = {"uk": "Українська", "ru": "Русский"}
_ROLE_LABELS = {ROLE_TRAINER: "Тренер", ROLE_ATHLETE: "Спортсмен"}


class Onboarding(StatesGroup):
    """FSM states for onboarding."""

    choosing_role = State()
    entering_name = State()
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


def _format_profile(profile: UserProfile) -> str:
    role_label = _ROLE_LABELS.get(profile.role, profile.role.title())
    language_label = _LANGUAGE_LABELS.get(profile.language, profile.language)
    group_line = profile.group_name or "—"
    return (
        "Ваш профиль готов!\n"
        f"Роль: <b>{role_label}</b>\n"
        f"Имя: <b>{profile.full_name}</b>\n"
        f"Группа: <b>{group_line}</b>\n"
        f"Язык: <b>{language_label}</b>"
    )


@router.message(CommandStart())
async def start_onboarding(
    message: Message,
    state: FSMContext,
    user_service: UserService,
    role_service: RoleService,
) -> None:
    """Handle /start: run onboarding or show profile."""

    await state.clear()
    user_id = message.from_user.id
    profile = await user_service.get_profile(user_id)
    if profile:
        await role_service.set_role(user_id, profile.role)
        await message.answer(
            _format_profile(profile), reply_markup=build_menu_keyboard(profile.role)
        )
        return

    await state.set_state(Onboarding.choosing_role)
    await message.answer(
        "Привет! Давайте настроим ваш профиль. Выберите вашу роль:",
        reply_markup=get_onboarding_role_keyboard(),
    )
    return


@router.callback_query(Onboarding.choosing_role, OnboardingRoleCB.filter())
async def process_role(
    callback: CallbackQuery,
    callback_data: OnboardingRoleCB,
    state: FSMContext,
) -> None:
    """Save chosen role and ask for name."""

    role = callback_data.role
    await state.update_data(role=role)
    await state.set_state(Onboarding.entering_name)
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        "Отлично! Теперь введите ваше имя и фамилию (2-64 символа, без спецсимволов)."
    )
    await callback.answer()


@router.message(Onboarding.entering_name, F.text)
async def process_name(message: Message, state: FSMContext) -> None:
    """Validate and store user name."""

    name = message.text or ""
    cleaned = _validate_name(name)
    if not cleaned:
        await message.answer(
            "Имя должно содержать от 2 до 64 символов и не включать спецсимволы."
        )
        return
    await state.update_data(full_name=cleaned)
    await state.set_state(Onboarding.entering_group)
    await message.answer(
        "Укажите группу/клуб (опционально) или пропустите шаг:",
        reply_markup=get_onboarding_skip_keyboard(),
    )


async def _proceed_to_language(state: FSMContext, message: Message) -> None:
    await state.set_state(Onboarding.choosing_language)
    await message.answer(
        "Выберите язык интерфейса:",
        reply_markup=get_onboarding_language_keyboard(),
    )


@router.message(Onboarding.entering_group, F.text)
async def process_group(message: Message, state: FSMContext) -> None:
    """Store provided group or skip if requested."""

    text = message.text or ""
    if text.casefold() in {"пропустить", "skip", "-"}:
        await state.update_data(group_name=None)
    else:
        cleaned = text.strip()
        if cleaned:
            await state.update_data(group_name=cleaned[:80])
        else:
            await state.update_data(group_name=None)
    await message.answer("Шаг сохранён.")
    await _proceed_to_language(state, message)


@router.callback_query(Onboarding.entering_group, F.data == "onboard_skip_group")
async def skip_group_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle inline skip for group step."""

    await state.update_data(group_name=None)
    await callback.message.edit_reply_markup()
    await callback.answer("Пропущено")
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
        await callback.answer("Произошла ошибка, начните заново.", show_alert=True)
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
    profile = await user_service.get_profile(user_id)
    await state.clear()
    await callback.message.edit_reply_markup()
    if profile:
        await callback.message.answer(
            _format_profile(profile), reply_markup=build_menu_keyboard(profile.role)
        )
    else:
        await callback.message.answer(
            "Профиль сохранён.", reply_markup=build_menu_keyboard(role)
        )
    await callback.answer("Готово!")
