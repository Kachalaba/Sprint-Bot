"""Role-aware menu handlers."""

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from role_service import ROLE_ADMIN, ROLE_ATHLETE, ROLE_TRAINER, RoleService
from utils.roles import require_roles

router = Router()

_MENU_TEXT = "Выберите раздел:"  # TODO: подключить i18n при доступности


def _row(*buttons: InlineKeyboardButton) -> list[InlineKeyboardButton]:
    return list(buttons)


def _menu_keyboard_for_manager() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _row(InlineKeyboardButton(text="Добавить результат", callback_data="menu_sprint")),
            _row(InlineKeyboardButton(text="Шаблоны", callback_data="menu_templates")),
            _row(InlineKeyboardButton(text="Отчёты", callback_data="menu_reports")),
            _row(InlineKeyboardButton(text="Поиск/История", callback_data="menu_history")),
        ]
    )


def _menu_keyboard_for_athlete() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _row(InlineKeyboardButton(text="Мои результаты", callback_data="menu_history")),
            _row(InlineKeyboardButton(text="Мой прогресс", callback_data="menu_progress")),
        ]
    )


def build_menu_keyboard(role: str) -> InlineKeyboardMarkup:
    """Return inline keyboard for the provided role."""

    if role == ROLE_ATHLETE:
        return _menu_keyboard_for_athlete()
    keyboard = _menu_keyboard_for_manager()
    if role == ROLE_ADMIN:
        keyboard.inline_keyboard.append(
            _row(InlineKeyboardButton(text="Админ-раздел", callback_data="menu_admin"))
        )
    return keyboard


async def _resolve_role(message: types.Message, role_service: RoleService, user_role: str | None) -> str:
    await role_service.upsert_user(message.from_user)
    if user_role:
        return user_role
    return await role_service.get_role(message.from_user.id)


async def _send_menu(
    message: types.Message, role_service: RoleService, user_role: str | None
) -> None:
    role = await _resolve_role(message, role_service, user_role)
    await message.answer(_MENU_TEXT, reply_markup=build_menu_keyboard(role))


@router.message(CommandStart())
async def cmd_start(
    message: types.Message, role_service: RoleService, user_role: str | None = None
) -> None:
    """Show menu depending on user role."""

    await _send_menu(message, role_service, user_role)


@router.message(Command("menu"))
async def cmd_menu(
    message: types.Message, role_service: RoleService, user_role: str | None = None
) -> None:
    """Explicit command to reopen main menu."""

    await _send_menu(message, role_service, user_role)


@router.message(F.text == "Старт")
async def start_button(
    message: types.Message, role_service: RoleService, user_role: str | None = None
) -> None:
    """Handle reply keyboard start button."""

    await _send_menu(message, role_service, user_role)


@router.callback_query(F.data == "menu_reports")
@require_roles(ROLE_TRAINER, ROLE_ADMIN)
async def menu_reports(cb: types.CallbackQuery) -> None:
    """Placeholder for coach/admin report section."""

    await cb.message.answer("Раздел отчётов находится в разработке.")
    await cb.answer()


@router.callback_query(F.data == "menu_progress")
async def menu_progress_redirect(
    cb: types.CallbackQuery, role_service: RoleService
) -> None:
    """Redirect progress menu button to the existing progress flow."""

    from handlers.progress import cmd_progress

    await cmd_progress(cb.message, role_service)
    await cb.answer()
