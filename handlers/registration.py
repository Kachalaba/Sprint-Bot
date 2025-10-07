from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from aiogram import F, Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from handlers.menu import build_menu_keyboard
from menu_callbacks import CB_MENU_INVITE
from role_service import ROLE_ATHLETE, ROLE_TRAINER, RoleService
from services import get_bot, ws_athletes
from utils.roles import require_roles

logger = logging.getLogger(__name__)

router = Router()

# In-memory storage for invite codes
active_invites: dict[str, int] = {}


class RegStates(StatesGroup):
    """FSM states for athlete registration."""

    waiting_for_name = State()


@router.callback_query(require_roles(ROLE_TRAINER), F.data == CB_MENU_INVITE)
async def send_invite(cb: types.CallbackQuery, role_service: RoleService) -> None:
    """Generate one-time invite link for a coach."""

    await role_service.upsert_user(cb.from_user, default_role=ROLE_TRAINER)
    code = secrets.token_hex(4)
    active_invites[code] = cb.from_user.id
    bot = get_bot()
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=\u0440\u0435\u0433_{code}"

    await cb.message.answer(f"Надішліть спортсмену це посилання:\n{link}")
    await cb.answer()


@router.message(CommandStart(deep_link=True))
async def start_with_code(
    message: types.Message,
    command: CommandStart.CommandObject,
    state: FSMContext,
    role_service: RoleService,
) -> None:  # type: ignore[attr-defined]
    """Handle /start with invite code."""
    args = command.args
    if not args or not args.startswith("\u0440\u0435\u0433_"):
        return

    code = args.split("_", 1)[1]
    if code not in active_invites:
        await message.answer("Це посилання більше не дійсне.")
        return

    await state.set_state(RegStates.waiting_for_name)
    await state.update_data(code=code, trainer_id=active_invites.get(code))
    await message.answer("Вітаємо! Введіть ваше ім'я та прізвище.")


@router.message(RegStates.waiting_for_name)
async def process_name(
    message: types.Message, state: FSMContext, role_service: RoleService
) -> None:
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
    trainer_id = data.get("trainer_id")
    await role_service.upsert_user(message.from_user, default_role=ROLE_ATHLETE)
    await role_service.set_role(message.from_user.id, ROLE_ATHLETE)
    if trainer_id:
        await role_service.set_trainer(message.from_user.id, int(trainer_id))
    await state.clear()
    await message.answer(
        f"✅ {name} зареєстрований!", reply_markup=build_menu_keyboard(ROLE_ATHLETE)
    )
