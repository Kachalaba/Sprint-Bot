from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from role_service import ROLE_ADMIN, ROLE_ATHLETE, ROLE_TRAINER, RoleService
from services import get_athletes_worksheet
from utils.roles import require_roles

router = Router()

start_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Старт"),
        ],
        [KeyboardButton(text="Реєстрація")],
    ],
    resize_keyboard=True,
)


@router.message(Command("reg"), require_roles(ROLE_TRAINER, ROLE_ADMIN))
@router.message(
    require_roles(ROLE_TRAINER, ROLE_ADMIN), lambda m: m.text == "Реєстрація"
)
async def cmd_reg(message: types.Message) -> None:
    """Request athlete contact."""
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Надішліть контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Надішліть контакт спортсмена:", reply_markup=kb)


@router.message(lambda m: m.contact is not None)
async def reg_contact(message: types.Message, role_service: RoleService) -> None:
    """Save athlete contact."""
    contact = message.contact
    try:
        worksheet = get_athletes_worksheet()
    except RuntimeError:
        await message.answer(
            "Не вдалося отримати доступ до таблиці спортсменів. Спробуйте пізніше."
        )
        return

    try:
        worksheet.append_row(
            [
                contact.user_id,
                contact.first_name or "",
                datetime.now(timezone.utc).isoformat(" ", "seconds"),
            ]
        )
    except Exception:
        return await message.answer(
            "Помилка при збереженні контакту. Спробуйте пізніше."
        )
    await role_service.set_role(contact.user_id, ROLE_ATHLETE)
    await role_service.upsert_user(contact)
    await message.answer(
        f"✅ Спортсмен {contact.first_name} зареєстрований.",
        reply_markup=start_kb,
    )
