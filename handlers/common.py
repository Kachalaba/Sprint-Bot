from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from filters import RoleFilter
from keyboards import get_main_keyboard
from role_service import ROLE_ADMIN, ROLE_ATHLETE, ROLE_TRAINER, RoleService
from services import ws_athletes

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


@router.message(Command("reg"), RoleFilter(ROLE_TRAINER, ROLE_ADMIN))
@router.message(RoleFilter(ROLE_TRAINER, ROLE_ADMIN), lambda m: m.text == "Реєстрація")
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
        ws_athletes.append_row(
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


@router.message(Command("start"))
@router.message(lambda m: m.text == "Старт")
async def cmd_start(message: types.Message, role_service: RoleService) -> None:
    """Show main menu."""
    await role_service.upsert_user(message.from_user)
    role = await role_service.get_role(message.from_user.id)
    await message.answer("Оберіть розділ:", reply_markup=get_main_keyboard(role))
