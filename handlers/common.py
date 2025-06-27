from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from services import ADMIN_IDS, ws_athletes

router = Router()

start_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Старт"),
        ],
        [KeyboardButton(text="Регистрация")],
    ],
    resize_keyboard=True,
)


@router.message(Command("reg"))
@router.message(lambda m: m.text == "Регистрация")
async def cmd_reg(message: types.Message) -> None:
    """Request athlete contact."""
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Перешлите контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Перешлите контакт спортсмена:", reply_markup=kb)


@router.message(lambda m: m.contact is not None)
async def reg_contact(message: types.Message) -> None:
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
        return await message.answer("Ошибка при сохранении контакта. Попробуйте позже.")
    await message.answer(
        f"✅ Спортсмен {contact.first_name} зарегистрирован.",
        reply_markup=start_kb,
    )


@router.message(Command("start"))
@router.message(lambda m: m.text == "Старт")
async def cmd_start(message: types.Message) -> None:
    """Show main menu."""
    inline_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Спринт", callback_data="menu_sprint")],
            [InlineKeyboardButton(text="Стаер", callback_data="menu_stayer")],
            [InlineKeyboardButton(text="История", callback_data="menu_history")],
            [InlineKeyboardButton(text="Рекорды", callback_data="menu_records")],
            *(
                [[InlineKeyboardButton(text="Admin", callback_data="menu_admin")]]
                if message.from_user.id in ADMIN_IDS
                else []
            ),
        ]
    )
    await message.answer("Выбери раздел:", reply_markup=inline_kb)
