from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from aiogram import F, Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards import get_main_keyboard
from services import ADMIN_IDS, bot, ws_athletes

logger = logging.getLogger(__name__)

router = Router()

# In-memory storage for invite codes
active_invites: dict[str, int] = {}


class RegStates(StatesGroup):
    """FSM states for athlete registration."""

    waiting_for_name = State()


@router.callback_query(F.data == "invite")
async def send_invite(cb: types.CallbackQuery) -> None:
    """Generate one-time invite link for a coach."""
    if str(cb.from_user.id) not in ADMIN_IDS:
        return await cb.answer("Недостатньо прав.", show_alert=True)

    code = secrets.token_hex(4)
    active_invites[code] = cb.from_user.id
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=\u0440\u0435\u0433_{code}"

    await cb.message.answer(f"Надішліть спортсмену це посилання:\n{link}")
    await cb.answer()


@router.message(CommandStart(deep_link=True))
async def start_with_code(message: types.Message, command: CommandStart.CommandObject, state: FSMContext) -> None:  # type: ignore[attr-defined]
    """Handle /start with invite code."""
    args = command.args
    if not args or not args.startswith("\u0440\u0435\u0433_"):
        return

    code = args.split("_", 1)[1]
    if code not in active_invites:
        await message.answer("Це посилання більше не дійсне.")
        return

    await state.set_state(RegStates.waiting_for_name)
    await state.update_data(code=code)
    await message.answer("Вітаємо! Введіть ваше ім'я та прізвище.")


@router.message(RegStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext) -> None:
    """Save athlete name and finish registration."""
    data = await state.get_data()
    code = data.get("code")
    name = message.text or ""
    try:
        ws_athletes.append_row(
            [
                message.from_user.id,
                name,
                datetime.now(timezone.utc).isoformat(" ", "seconds"),
            ]
        )
    except Exception as e:
        logger.error(f"Failed to add athlete: {e}")
        await message.answer("Сталася помилка при збереженні. Спробуйте пізніше.")
        return

    active_invites.pop(code, None)
    await state.clear()
    await message.answer(
        f"✅ {name} зареєстрований!", reply_markup=get_main_keyboard(is_admin=False)
    )
