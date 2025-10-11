"""Admin panel handlers providing role and group management."""

from __future__ import annotations

import asyncio
import csv
import io
import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from handlers.admin_browser import (
    DEBUG_BROWSE_CALLBACK,
    build_history_table,
    build_pb_table,
    get_admin_summary,
    group_history,
    render_progress_chart,
)
from i18n import t
from menu_callbacks import CB_MENU_ADMIN
from role_service import ROLE_ADMIN, ROLE_ATHLETE, ROLE_TRAINER, RoleService
from services import get_registered_athletes
from services.export_service import ExportService
from services.io_service import IOService
from services.query_service import QueryService
from services.stats_service import StatsService
from utils.roles import require_roles

logger = logging.getLogger(__name__)
router = Router()


class AdminStates(StatesGroup):
    """FSM states for role assignment flows."""

    waiting_user_id = State()
    waiting_role_choice = State()
    waiting_athlete_id = State()
    waiting_trainer_choice = State()


_DEBUG_BADGE_KEY = "admin.debug.badge"
_DEBUG_MENU_CALLBACK = "admin:debug"
_DEBUG_FORCE_SYNC_CALLBACK = "admin:debug:sync"
_DEBUG_EXPORT_CALLBACK = "admin:debug:export"
_DEBUG_SIMULATE_CALLBACK = "admin:debug:simulate"

_QA_EXPORT_SERVICE = ExportService()


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
            [
                InlineKeyboardButton(
                    text="🧪 Debug / QA", callback_data=_DEBUG_MENU_CALLBACK
                )
            ],
        ]
    )


def _debug_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👟 Athlete Browser", callback_data=DEBUG_BROWSE_CALLBACK
                )
            ],
            [
                InlineKeyboardButton(
                    text="📤 Export All", callback_data=_DEBUG_EXPORT_CALLBACK
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Force Sync", callback_data=_DEBUG_FORCE_SYNC_CALLBACK
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧍‍♂️ Simulate Athlete", callback_data=_DEBUG_SIMULATE_CALLBACK
                )
            ],
        ]
    )


async def _sync_all_services(
    role_service: RoleService,
    stats_service: StatsService,
    query_service: QueryService,
    io_service: IOService,
) -> int:
    """Re-run initialisation for local storages and refresh athlete list."""

    await role_service.init()
    await asyncio.gather(
        stats_service.init(),
        query_service.init(),
        io_service.init(),
    )
    dataset = get_registered_athletes()
    if dataset:
        await role_service.bulk_sync_athletes(tuple(dataset))
    return len(dataset)


async def _generate_full_export(role_service: RoleService) -> tuple[bytes, list[int]]:
    """Collect QA export payload for every athlete."""

    athletes = await role_service.list_users(roles=(ROLE_ATHLETE,))
    athlete_ids = [user.telegram_id for user in athletes]
    if not athlete_ids:
        return b"", []
    payload = await _QA_EXPORT_SERVICE.export_pb_sob(athlete_ids)
    return payload, athlete_ids


async def _send_summary(target: types.Message, summary) -> None:
    """Render summary message and chart for provided admin snapshot."""

    history_text = build_history_table(summary.history)
    pb_text = build_pb_table(summary.pb_rows)
    header = (
        f"{t(_DEBUG_BADGE_KEY)}\n<b>{summary.full_name}</b> (ID {summary.athlete_id})\n"
        f"{t('admin.browser.weekly_summary', attempts=summary.weekly_attempts, prs=summary.weekly_prs)}"
    )
    await target.answer(f"{header}\n\n{pb_text}\n\n{history_text}", parse_mode="HTML")
    chart = render_progress_chart(group_history(summary.history))
    if chart:
        document = BufferedInputFile(
            chart, filename=f"athlete_{summary.athlete_id}_progress.png"
        )
        await target.answer_photo(document, caption=t("admin.browser.chart.caption"))


def _parse_athlete_csv(content: bytes) -> list[tuple[int, str]]:
    """Parse uploaded CSV file into athlete tuples."""

    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    items: list[tuple[int, str]] = []
    for index, row in enumerate(reader):
        if not row:
            continue
        try:
            first_cell = row[0].strip()
        except (AttributeError, IndexError):
            continue
        if index == 0 and first_cell.lower() in {"athlete_id", "id"}:
            continue
        try:
            athlete_id = int(first_cell)
        except ValueError:
            continue
        name = row[1].strip() if len(row) > 1 and row[1] else f"ID {athlete_id}"
        items.append((athlete_id, name))
    return items


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


@router.message(Command("admin"), require_roles(ROLE_ADMIN))
@router.callback_query(require_roles(ROLE_ADMIN), F.data == CB_MENU_ADMIN)
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


@router.callback_query(require_roles(ROLE_ADMIN), F.data == _DEBUG_MENU_CALLBACK)
async def open_debug_menu(cb: types.CallbackQuery) -> None:
    """Show QA/debug shortcuts for administrators."""

    await _answer(
        cb,
        f"{t(_DEBUG_BADGE_KEY)}\n{t('admin.debug.menu_title')}",
        reply_markup=_debug_keyboard(),
    )


@router.callback_query(require_roles(ROLE_ADMIN), F.data == _DEBUG_FORCE_SYNC_CALLBACK)
async def trigger_force_sync_callback(
    cb: types.CallbackQuery,
    role_service: RoleService,
    stats_service: StatsService,
    query_service: QueryService,
    io_service: IOService,
) -> None:
    """Handle force sync request from debug menu."""

    await cb.answer()
    imported = await _sync_all_services(
        role_service, stats_service, query_service, io_service
    )
    await cb.message.answer(
        t(
            "admin.tools.force_sync_done",
            badge=t(_DEBUG_BADGE_KEY),
            count=imported,
        ),
        reply_markup=None,
    )


@router.callback_query(require_roles(ROLE_ADMIN), F.data == _DEBUG_EXPORT_CALLBACK)
async def trigger_export_callback(
    cb: types.CallbackQuery, role_service: RoleService
) -> None:
    """Send PB/SoB export via debug menu."""

    await cb.answer()
    payload, ids = await _generate_full_export(role_service)
    if not payload:
        await cb.message.answer(
            t("admin.tools.export_empty", badge=t(_DEBUG_BADGE_KEY)),
            reply_markup=None,
        )
        return
    caption = t(
        "admin.tools.export_caption",
        badge=t(_DEBUG_BADGE_KEY),
        count=len(ids),
    )
    await cb.message.answer_document(
        BufferedInputFile(payload, filename="qa_export.csv"),
        caption=caption,
    )


@router.callback_query(require_roles(ROLE_ADMIN), F.data == _DEBUG_SIMULATE_CALLBACK)
async def trigger_simulate_callback(cb: types.CallbackQuery) -> None:
    """Explain how to run admin simulations."""

    await cb.answer()
    await cb.message.answer(
        t("admin.debug.simulate_hint", badge=t(_DEBUG_BADGE_KEY)),
        parse_mode="HTML",
    )


@router.message(Command("force_sync"), require_roles(ROLE_ADMIN))
async def force_sync_command(
    message: types.Message,
    role_service: RoleService,
    stats_service: StatsService,
    query_service: QueryService,
    io_service: IOService,
) -> None:
    """Manually rebuild caches and reload athlete registry."""

    imported = await _sync_all_services(
        role_service, stats_service, query_service, io_service
    )
    await message.answer(
        t(
            "admin.tools.force_sync_done",
            badge=t(_DEBUG_BADGE_KEY),
            count=imported,
        )
    )


@router.message(Command("admin_export"), require_roles(ROLE_ADMIN))
async def admin_export_command(
    message: types.Message, role_service: RoleService
) -> None:
    """Send PB/SoB analytics export to the admin."""

    payload, ids = await _generate_full_export(role_service)
    if not payload:
        await message.answer(t("admin.tools.export_empty", badge=t(_DEBUG_BADGE_KEY)))
        return
    await message.answer(
        t(
            "admin.tools.export_preparing",
            badge=t(_DEBUG_BADGE_KEY),
            count=len(ids),
        )
    )
    await message.answer_document(
        BufferedInputFile(payload, filename="qa_export.csv"),
        caption=t("admin.tools.export_ready"),
    )


@router.message(Command("admin_test"), require_roles(ROLE_ADMIN))
async def admin_test_command(
    message: types.Message,
    role_service: RoleService,
    stats_service: StatsService,
    query_service: QueryService,
) -> None:
    """Simulate bot features on behalf of another athlete."""

    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer(
            t("admin.tools.test_usage", badge=t(_DEBUG_BADGE_KEY)),
            parse_mode="HTML",
        )
        return

    feature = parts[1].lower()
    try:
        athlete_id = int(parts[2])
    except ValueError:
        await message.answer(t("res.invalid_id"))
        return

    if feature not in {"browser", "progress", "history"}:
        await message.answer(t("admin.tools.test_unknown", feature=feature))
        return

    summary = await get_admin_summary(
        role_service, query_service, stats_service, athlete_id
    )
    await _send_summary(message, summary)


@router.message(Command("import_athletes"), require_roles(ROLE_ADMIN))
async def import_athletes_command(
    message: types.Message, role_service: RoleService
) -> None:
    """Import athletes either from Google Sheet or uploaded CSV."""

    dataset: list[tuple[int, str]] = []
    document = message.document
    if document:
        buffer = io.BytesIO()
        await message.bot.download(document, destination=buffer)
        dataset = _parse_athlete_csv(buffer.getvalue())
    else:
        dataset = list(get_registered_athletes())

    if not dataset:
        await message.answer(t("admin.tools.import_empty", badge=t(_DEBUG_BADGE_KEY)))
        return

    await role_service.bulk_sync_athletes(dataset)
    await message.answer(
        t(
            "admin.tools.import_done",
            badge=t(_DEBUG_BADGE_KEY),
            count=len(dataset),
        )
    )


@router.callback_query(require_roles(ROLE_ADMIN), F.data == "admin:users")
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


@router.callback_query(require_roles(ROLE_ADMIN), F.data == "admin:set")
async def ask_user_for_role(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Ask admin to provide user id for role change."""

    await state.set_state(AdminStates.waiting_user_id)
    await cb.message.answer("Введіть Telegram ID користувача для зміни ролі:")
    await cb.answer()


@router.message(AdminStates.waiting_user_id, require_roles(ROLE_ADMIN))
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
    require_roles(ROLE_ADMIN),
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


@router.callback_query(require_roles(ROLE_ADMIN), F.data == "admin:bind")
async def ask_athlete(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Request athlete id to assign a trainer."""

    await state.set_state(AdminStates.waiting_athlete_id)
    await cb.message.answer("Введіть ID спортсмена для призначення тренера:")
    await cb.answer()


@router.message(AdminStates.waiting_athlete_id, require_roles(ROLE_ADMIN))
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
    require_roles(ROLE_ADMIN),
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
