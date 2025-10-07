"""Role-aware menu handlers with redesigned interface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from i18n import t
from keyboards import (
    build_contextual_greeting,
    build_modern_main_menu,
    get_quick_actions_keyboard,
)
from menu_callbacks import (
    CB_MENU_ADMIN,
    CB_MENU_MY_RECENT_PRS,
    CB_MENU_NOOP,
    CB_MENU_PROGRESS,
    CB_MENU_QUICK_ADD_RESULT,
    CB_MENU_REPORTS,
    CB_MENU_TEAM_SUMMARY,
    CB_MENU_TODAY_TRAINING,
)
from role_service import ROLE_ADMIN, ROLE_ATHLETE, ROLE_TRAINER, RoleService
from services.stats_service import LatestResult, StatsPeriod, StatsService
from utils import fmt_time
from utils.roles import require_roles

router = Router()

_MENU_TEXT_KEY = "menu.modern_title"
_DEFAULT_TIMEZONE = "Europe/Kyiv"


@dataclass(slots=True)
class _MenuContext:
    """Precomputed context data used for rendering the menu."""

    time_of_day: str
    current_date: str
    current_time: str
    unread_messages: int = 0
    pending_actions: int = 0
    recent_activity: str | None = None
    upcoming_event: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return dict representation for keyboard builders."""

        return {
            "time_of_day": self.time_of_day,
            "current_date": self.current_date,
            "current_time": self.current_time,
            "unread_messages": self.unread_messages,
            "pending_actions": self.pending_actions,
            "recent_activity": self.recent_activity,
            "upcoming_event": self.upcoming_event,
        }


def build_menu_keyboard(role: str) -> types.InlineKeyboardMarkup:
    """Backward compatible menu keyboard builder."""

    context = _MenuContext(
        time_of_day="day",
        current_date="",
        current_time="",
    )
    return build_modern_main_menu(role, user_name="", context_data=context.as_dict())


def _classify_time_of_day(moment: datetime) -> str:
    """Return textual time-of-day bucket for contextual messaging."""

    hour = moment.hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def _localized_now(tz_name: str) -> datetime:
    """Return localized current datetime with graceful fallback."""

    try:
        return datetime.now(ZoneInfo(tz_name))
    except ZoneInfoNotFoundError:
        return datetime.utcnow()


def _format_recent_activity(latest: LatestResult | None) -> str | None:
    """Build localized string describing the latest athlete result."""

    if latest is None:
        return None
    timestamp = latest.timestamp.strftime("%d.%m %H:%M")
    try:
        stroke = t(f"stroke.{latest.stroke.lower()}")
    except KeyError:
        stroke = latest.stroke
    return t(
        "menu.summary.recent_result",
        stroke=stroke,
        distance=latest.distance,
        time=fmt_time(latest.total_seconds),
        timestamp=timestamp,
    )


async def _build_context_data(
    role: str, user_id: int, stats_service: StatsService
) -> _MenuContext:
    """Prepare contextual information for menu rendering."""

    now = _localized_now(_DEFAULT_TIMEZONE)
    latest_result: LatestResult | None = None
    if role == ROLE_ATHLETE:
        latest_result = await stats_service.latest_result(user_id)

    recent_activity = _format_recent_activity(latest_result)

    return _MenuContext(
        time_of_day=_classify_time_of_day(now),
        current_date=now.strftime("%d %B"),
        current_time=now.strftime("%H:%M"),
        unread_messages=0,
        pending_actions=0 if role == ROLE_ATHLETE else 0,
        recent_activity=recent_activity,
        upcoming_event=None,
    )


async def _resolve_role(
    message: types.Message, role_service: RoleService, user_role: str | None
) -> str:
    await role_service.upsert_user(message.from_user)
    if user_role:
        return user_role
    return await role_service.get_role(message.from_user.id)


async def _send_menu(
    message: types.Message,
    role_service: RoleService,
    stats_service: StatsService,
    user_role: str | None,
) -> None:
    role = await _resolve_role(message, role_service, user_role)
    user_name = message.from_user.full_name
    context = await _build_context_data(role, message.from_user.id, stats_service)

    greeting = build_contextual_greeting(user_name, context.time_of_day)

    summary_lines = [
        t(
            "menu.summary.current_time",
            date=context.current_date,
            time=context.current_time,
        )
    ]
    if context.recent_activity:
        summary_lines.append(context.recent_activity)
    else:
        summary_lines.append(t("menu.summary.no_recent_activity"))
    if context.upcoming_event:
        summary_lines.append(
            t("menu.summary.upcoming_event", event=context.upcoming_event)
        )
    else:
        summary_lines.append(t("menu.summary.no_upcoming_events"))

    quick_actions = get_quick_actions_keyboard(message.from_user.id, role)
    await message.answer(
        "\n".join([greeting, *summary_lines]),
        reply_markup=quick_actions,
    )

    await message.answer(
        t(_MENU_TEXT_KEY),
        reply_markup=build_modern_main_menu(
            role, user_name=user_name, context_data=context.as_dict()
        ),
    )


@router.message(Command("menu"))
async def cmd_menu(
    message: types.Message,
    role_service: RoleService,
    stats_service: StatsService,
    user_role: str | None = None,
) -> None:
    """Explicit command to reopen main menu."""

    await _send_menu(message, role_service, stats_service, user_role)


@router.message(CommandStart())
async def cmd_start(
    message: types.Message,
    role_service: RoleService,
    stats_service: StatsService,
    user_role: str | None = None,
) -> None:
    """Handle reply keyboard start button."""

    await _send_menu(message, role_service, stats_service, user_role)


@router.callback_query(
    require_roles(ROLE_TRAINER, ROLE_ADMIN), F.data == CB_MENU_REPORTS
)
async def menu_reports(cb: types.CallbackQuery) -> None:
    """Placeholder for coach/admin report section."""

    await cb.message.answer(t("menu.reports_in_development"))
    await cb.answer()


@router.callback_query(F.data == CB_MENU_PROGRESS)
async def menu_progress_redirect(
    cb: types.CallbackQuery, role_service: RoleService, stats_service: StatsService
) -> None:
    """Redirect progress menu button to the existing progress flow."""

    from handlers.progress import cmd_progress

    await cmd_progress(cb.message, role_service, stats_service)
    await cb.answer()


@router.callback_query(F.data == CB_MENU_QUICK_ADD_RESULT)
async def menu_quick_add_result(
    cb: types.CallbackQuery, state: FSMContext, role_service: RoleService
) -> None:
    """Proxy quick action to the existing add-result flow."""

    from handlers.sprint_actions import menu_sprint

    await menu_sprint(cb, state, role_service)
    await cb.answer()


@router.callback_query(F.data == CB_MENU_MY_RECENT_PRS)
async def menu_recent_prs(
    cb: types.CallbackQuery,
    stats_service: StatsService,
) -> None:
    """Show weekly highlight summary for athlete quick action."""

    progress = await stats_service.weekly_progress(cb.from_user.id, limit=3)
    if progress.pr_count == 0:
        await cb.message.answer(t("menu.quick_actions.no_recent_prs"))
        await cb.answer()
        return

    highlights = []
    for item in progress.highlights:
        highlight = t(
            "menu.quick_actions.pr_item",
            stroke=item.stroke,
            distance=item.distance,
            time=fmt_time(item.total_seconds),
        )
        highlights.append(highlight)

    summary = t(
        "menu.quick_actions.recent_prs_summary",
        count=progress.pr_count,
        attempts=progress.attempts,
    )
    await cb.message.answer("\n".join([summary, *highlights]))
    await cb.answer()


@router.callback_query(F.data == CB_MENU_TEAM_SUMMARY)
async def menu_team_summary(
    cb: types.CallbackQuery, stats_service: StatsService
) -> None:
    """Provide quick leaderboard snapshot for trainers."""

    entries = await stats_service.leaderboard(StatsPeriod.WEEK, limit=3)
    if not entries:
        await cb.message.answer(t("menu.quick_actions.no_team_summary"))
        await cb.answer()
        return

    rows = [t("menu.quick_actions.team_summary_header")]
    for place, entry in enumerate(entries, start=1):
        rows.append(
            t(
                "menu.quick_actions.team_summary_item",
                place=place,
                name=entry.athlete_name,
                prs=entry.pr_count,
                attempts=entry.attempts,
            )
        )
    await cb.message.answer("\n".join(rows))
    await cb.answer()


@router.callback_query(F.data == CB_MENU_TODAY_TRAINING)
async def menu_today_training(cb: types.CallbackQuery) -> None:
    """Show placeholder for today's training schedule quick action."""

    await cb.message.answer(t("menu.quick_actions.today_training_hint"))
    await cb.answer()


@router.callback_query(F.data == CB_MENU_NOOP)
async def menu_noop(cb: types.CallbackQuery) -> None:
    """Absorb separator button callbacks to avoid errors."""

    await cb.answer()
