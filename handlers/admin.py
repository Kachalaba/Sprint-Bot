"""Admin panel handlers providing role and group management."""

from __future__ import annotations

import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from filters import RoleFilter
from role_service import ROLE_ADMIN, ROLE_ATHLETE, ROLE_TRAINER, RoleService

logger = logging.getLogger(__name__)
router = Router()


class AdminStates(StatesGroup):
    """FSM states for role assignment flows."""

    waiting_user_id = State()
    waiting_role_choice = State()
    waiting_athlete_id = State()
    waiting_trainer_choice = State()


def _admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Користувачі", callback_data="admin:users")],
            [
                InlineKeyboardButton(
                    text="🎯 Призначити роль", callback_data="admin:set"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤝 Тренер спортсмену", callback_data="admin:bind"
                )
            ],
        ]
    )


async def _answer(
    event: types.Message | types.CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if isinstance(event, types.Message):
        await event.answer(text, reply_markup=reply_markup)
    else:
        await event.message.answer(text, reply_markup=reply_markup)
        await event.answer()


@router.message(Command("admin"), RoleFilter(ROLE_ADMIN))
@router.callback_query(RoleFilter(ROLE_ADMIN), F.data == "menu_admin")
async def open_admin_panel(
    event: types.Message | types.CallbackQuery, state: FSMContext
) -> None:
    """Show root admin menu."""

    await state.clear()
    await _answer(
        event,
        "<b>Адмін‑панель</b>\n"
        "Керуйте ролями користувачів та призначайте тренерів спортсменам.",
        reply_markup=_admin_keyboard(),
    )


@router.callback_query(RoleFilter(ROLE_ADMIN), F.data == "admin:users")
async def list_users(cb: types.CallbackQuery, role_service: RoleService) -> None:
    """Display current users grouped by roles."""

    users = await role_service.list_users()
    if not users:
        await cb.message.answer("Схоже, у базі поки немає користувачів.")
        await cb.answer()
        return

    lines: list[str] = ["<b>Користувачі за ролями</b>"]
    current_role: str | None = None
    for user in users:
        if user.role != current_role:
            current_role = user.role
            lines.append(f"\n<b>{current_role.title()}:</b>")
        lines.append(f"• {user.short_label}")
    await cb.message.answer("\n".join(lines))
    await cb.answer()


@router.callback_query(RoleFilter(ROLE_ADMIN), F.data == "admin:set")
async def ask_user_for_role(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Ask admin to provide user id for role change."""

    await state.set_state(AdminStates.waiting_user_id)
    await cb.message.answer("Введіть Telegram ID користувача для зміни ролі:")
    await cb.answer()


@router.message(AdminStates.waiting_user_id, RoleFilter(ROLE_ADMIN))
async def select_role_target(
    message: types.Message, state: FSMContext, role_service: RoleService
) -> None:
    """Store target user id and prompt for new role."""

    try:
        user_id = int(message.text.strip())
    except (TypeError, ValueError):
        await message.answer("ID має бути числом. Спробуйте ще раз:")
        return

    await state.update_data(target_id=user_id)
    user = next(
        (u for u in await role_service.list_users() if u.telegram_id == user_id), None
    )
    if user is None:
        await message.answer(
            "Користувача ще не було в базі. Після призначення ролі він буде створений."
        )

    buttons = [
        InlineKeyboardButton(text="👟 Спортсмен", callback_data="admin:role:athlete"),
        InlineKeyboardButton(text="🥇 Тренер", callback_data="admin:role:trainer"),
        InlineKeyboardButton(text="🛡 Адмін", callback_data="admin:role:admin"),
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=[[btn] for btn in buttons])
    await message.answer("Оберіть нову роль:", reply_markup=markup)
    await state.set_state(AdminStates.waiting_role_choice)


@router.callback_query(
    AdminStates.waiting_role_choice,
    RoleFilter(ROLE_ADMIN),
    F.data.startswith("admin:role:"),
)
async def apply_role_change(
    cb: types.CallbackQuery, state: FSMContext, role_service: RoleService
) -> None:
    """Persist selected role for target user."""

    data = await state.get_data()
    user_id = data.get("target_id")
    if not user_id:
        await cb.answer("Спочатку оберіть користувача.", show_alert=True)
        return

    role = cb.data.split(":", 2)[-1]
    mapping = {
        "athlete": ROLE_ATHLETE,
        "trainer": ROLE_TRAINER,
        "admin": ROLE_ADMIN,
    }
    if role not in mapping:
        await cb.answer("Невідома роль.", show_alert=True)
        return

    await role_service.set_role(int(user_id), mapping[role])
    await cb.message.answer(
        f"✅ Роль користувача <code>{user_id}</code> змінено на {mapping[role]}"
    )
    await state.clear()
    await cb.answer()


@router.callback_query(RoleFilter(ROLE_ADMIN), F.data == "admin:bind")
async def ask_athlete(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Request athlete id to assign a trainer."""

    await state.set_state(AdminStates.waiting_athlete_id)
    await cb.message.answer("Введіть ID спортсмена для призначення тренера:")
    await cb.answer()


@router.message(AdminStates.waiting_athlete_id, RoleFilter(ROLE_ADMIN))
async def choose_trainer(
    message: types.Message, state: FSMContext, role_service: RoleService
) -> None:
    """Show list of trainers for selected athlete."""

    try:
        athlete_id = int(message.text.strip())
    except (TypeError, ValueError):
        await message.answer("ID має бути числом. Спробуйте ще раз:")
        return

    athletes = await role_service.list_users(roles=(ROLE_ATHLETE,))
    if not any(user.telegram_id == athlete_id for user in athletes):
        await message.answer(
            "Спортсмена з таким ID не знайдено. Спершу зареєструйте його."
        )
        return

    trainers = await role_service.list_users(roles=(ROLE_TRAINER, ROLE_ADMIN))
    if not trainers:
        await message.answer("Немає доступних тренерів для призначення.")
        return

    await state.update_data(athlete_id=athlete_id)
    rows = [
        [
            InlineKeyboardButton(
                text=user.short_label, callback_data=f"admin:trainer:{user.telegram_id}"
            )
        ]
        for user in trainers
    ]
    await message.answer(
        "Оберіть тренера зі списку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await state.set_state(AdminStates.waiting_trainer_choice)


@router.callback_query(
    AdminStates.waiting_trainer_choice,
    RoleFilter(ROLE_ADMIN),
    F.data.startswith("admin:trainer:"),
)
async def apply_trainer_binding(
    cb: types.CallbackQuery, state: FSMContext, role_service: RoleService
) -> None:
    """Assign selected trainer to athlete."""

    data = await state.get_data()
    athlete_id = data.get("athlete_id")
    if not athlete_id:
        await cb.answer("Спочатку оберіть спортсмена.", show_alert=True)
        return

    trainer_id = int(cb.data.split(":", 2)[-1])
    await role_service.set_trainer(int(athlete_id), trainer_id)
    await cb.message.answer(
        "✅ Призначено тренера <code>{trainer}</code> для спортсмена <code>{athlete}</code>".format(
            trainer=trainer_id,
            athlete=athlete_id,
        )
    )
    await state.clear()
    await cb.answer()
