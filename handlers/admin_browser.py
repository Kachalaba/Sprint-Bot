"""Admin-facing athlete browser with analytics utilities."""

from __future__ import annotations

import asyncio
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

import matplotlib
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from i18n import t
from role_service import ROLE_ADMIN, ROLE_ATHLETE, RoleService, RoleUser
from services import get_athlete_name
from services.pb_service import get_sob, get_total_pb_attempt
from services.query_service import QueryService, SearchFilters, SearchResult
from services.stats_service import StatsService
from utils import fmt_time
from utils.logger import get_logger
from utils.roles import require_roles

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  # isort:skip

router = Router()
logger = get_logger(__name__)

SELECT_CALLBACK_PREFIX = "adminbrowse:athlete:"
DEBUG_BROWSE_CALLBACK = "admin:debug:browse"


@dataclass(slots=True)
class _AthleteSummary:
    """Aggregated snapshot about an athlete."""

    athlete_id: int
    full_name: str
    history: tuple[SearchResult, ...]
    pb_rows: tuple[tuple[str, int, float | None, float | None], ...]
    weekly_attempts: int
    weekly_prs: int


def _chunk_buttons(
    buttons: Iterable[InlineKeyboardButton], *, size: int = 2
) -> list[list[InlineKeyboardButton]]:
    """Split inline keyboard buttons into rows."""

    rows: list[list[InlineKeyboardButton]] = []
    buffer: list[InlineKeyboardButton] = []
    for button in buttons:
        buffer.append(button)
        if len(buffer) == size:
            rows.append(buffer.copy())
            buffer.clear()
    if buffer:
        rows.append(buffer.copy())
    return rows


async def _collect_history(
    query_service: QueryService,
    athlete_id: int,
    *,
    page_size: int = 25,
    max_pages: int = 6,
) -> tuple[SearchResult, ...]:
    """Fetch recent result history for an athlete."""

    page = 1
    collected: list[SearchResult] = []
    while page <= max_pages:
        result_page = await query_service.search_results(
            SearchFilters(athlete_id=athlete_id),
            page=page,
            page_size=page_size,
        )
        if not result_page.items:
            break
        collected.extend(result_page.items)
        if page >= result_page.pages:
            break
        page += 1
    return tuple(collected)


async def _collect_pb_rows(
    athlete_id: int,
    history: Sequence[SearchResult],
) -> tuple[tuple[str, int, float | None, float | None], ...]:
    """Return PB/SoB summary per stroke-distance pair."""

    unique_pairs: set[tuple[str, int]] = {
        (item.stroke, item.distance) for item in history
    }
    rows: list[tuple[str, int, float | None, float | None]] = []
    for stroke, distance in sorted(unique_pairs, key=lambda pair: (pair[0], pair[1])):
        pb = await asyncio.to_thread(get_total_pb_attempt, athlete_id, stroke, distance)
        sob = await asyncio.to_thread(get_sob, athlete_id, stroke, distance)
        rows.append(
            (
                stroke,
                distance,
                pb.total if pb else None,
                sob.total,
            )
        )
    return tuple(rows)


async def get_admin_summary(
    role_service: RoleService,
    query_service: QueryService,
    stats_service: StatsService,
    athlete_id: int,
) -> _AthleteSummary:
    """Gather all analytics required for the admin view."""

    logger.debug("Building admin summary", extra={"user_id": athlete_id})

    users = await role_service.list_users(roles=(ROLE_ATHLETE,))
    full_name = next(
        (
            user.full_name
            for user in users
            if user.telegram_id == athlete_id and user.full_name
        ),
        "",
    )
    if not full_name:
        resolved = get_athlete_name(athlete_id)
        if resolved:
            full_name = resolved
    if not full_name:
        full_name = f"ID {athlete_id}"

    history = await _collect_history(query_service, athlete_id)
    pb_rows = await _collect_pb_rows(athlete_id, history)

    weekly = await stats_service.weekly_progress(athlete_id)
    summary = _AthleteSummary(
        athlete_id=athlete_id,
        full_name=full_name,
        history=history,
        pb_rows=pb_rows,
        weekly_attempts=weekly.attempts,
        weekly_prs=weekly.pr_count,
    )
    return summary


def build_history_table(history: Sequence[SearchResult]) -> str:
    """Format history into a Markdown-friendly table."""

    if not history:
        return t("admin.browser.history.empty")

    lines = [t("admin.browser.history.title")]
    for item in history[:15]:
        attempt_date = item.timestamp.strftime("%Y-%m-%d %H:%M")
        pr_flag = t("admin.browser.history.pr_flag") if item.is_pr else ""
        lines.append(
            t(
                "admin.browser.history.entry",
                date=attempt_date,
                stroke=item.stroke,
                distance=item.distance,
                time=fmt_time(item.total_seconds),
                pr=pr_flag,
            )
        )
    if len(history) > 15:
        lines.append("…")
    return "\n".join(lines)


def build_pb_table(rows: Sequence[tuple[str, int, float | None, float | None]]) -> str:
    """Format PB/Sum of Best table."""

    if not rows:
        return t("admin.browser.pb.empty")
    lines = [t("admin.browser.pb.title")]
    for stroke, distance, pb_total, sob_total in rows:
        pieces = [t("admin.browser.pb.label", stroke=stroke, distance=distance)]
        if pb_total is not None:
            pieces.append(t("admin.browser.pb.pb", value=fmt_time(pb_total)))
        if sob_total is not None:
            pieces.append(t("admin.browser.pb.sob", value=fmt_time(sob_total)))
        lines.append(" — ".join(pieces))
    return "\n".join(lines)


def group_history(
    history: Sequence[SearchResult],
) -> dict[tuple[str, int], list[tuple[datetime, float]]]:
    grouped: dict[tuple[str, int], list[tuple[datetime, float]]] = defaultdict(list)
    for item in history:
        grouped[(item.stroke, item.distance)].append(
            (item.timestamp, item.total_seconds)
        )
    for values in grouped.values():
        values.sort(key=lambda pair: pair[0])
    return grouped


def render_progress_chart(
    grouped: dict[tuple[str, int], list[tuple[datetime, float]]],
) -> bytes | None:
    if not grouped:
        return None
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    for (stroke, distance), entries in grouped.items():
        dates = [item[0] for item in entries]
        totals = [item[1] for item in entries]
        label = t("admin.browser.chart.line_label", stroke=stroke, distance=distance)
        ax.plot(dates, totals, marker="o", linewidth=2, label=label)
    ax.set_title(t("admin.browser.chart.title"))
    ax.set_xlabel(t("admin.browser.chart.xlabel"))
    ax.set_ylabel(t("admin.browser.chart.ylabel"))
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()
    fig.autofmt_xdate()
    buffer = io.BytesIO()
    try:
        fig.tight_layout()
        fig.savefig(buffer, format="png")
    finally:
        plt.close(fig)
    return buffer.getvalue()


def _build_keyboard(athletes: Sequence[RoleUser]) -> InlineKeyboardMarkup:
    buttons: list[InlineKeyboardButton] = []
    for user in athletes:
        try:
            athlete_id = int(getattr(user, "telegram_id"))
        except (TypeError, ValueError):
            continue
        label = getattr(user, "full_name", "") or f"ID {athlete_id}"
        buttons.append(
            InlineKeyboardButton(
                text=f"{label} ({athlete_id})",
                callback_data=f"{SELECT_CALLBACK_PREFIX}{athlete_id}",
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=_chunk_buttons(buttons, size=2))


@router.message(Command("admin_athletes"), require_roles(ROLE_ADMIN))
async def cmd_admin_athletes(message: types.Message, role_service: RoleService) -> None:
    """Display inline athlete browser for administrators."""

    athletes = await role_service.list_users(roles=(ROLE_ATHLETE,))
    if not athletes:
        await message.answer(t("admin.browser.no_athletes"))
        return
    keyboard = _build_keyboard(athletes)
    await message.answer(
        f"{t('admin.debug.badge')}\n{t('admin.browser.select_prompt')}",
        reply_markup=keyboard,
    )


@router.callback_query(require_roles(ROLE_ADMIN), F.data == DEBUG_BROWSE_CALLBACK)
async def open_debug_browser(cb: CallbackQuery, role_service: RoleService) -> None:
    """Shortcut from debug menu to open athlete browser."""

    await cb.answer()
    athletes = await role_service.list_users(roles=(ROLE_ATHLETE,))
    if not athletes:
        await cb.message.answer(t("admin.browser.no_athletes"))
        return
    keyboard = _build_keyboard(athletes)
    await cb.message.answer(
        f"{t('admin.debug.badge')}\n{t('admin.browser.select_prompt')}",
        reply_markup=keyboard,
    )


@router.callback_query(
    require_roles(ROLE_ADMIN), F.data.startswith(SELECT_CALLBACK_PREFIX)
)
async def show_athlete_details(
    cb: CallbackQuery,
    role_service: RoleService,
    query_service: QueryService,
    stats_service: StatsService,
) -> None:
    """Render analytics for the selected athlete."""

    await cb.answer()
    raw_id = cb.data.replace(SELECT_CALLBACK_PREFIX, "", 1)
    try:
        athlete_id = int(raw_id)
    except ValueError:
        await cb.message.answer(t("admin.browser.invalid_id"))
        return

    summary = await get_admin_summary(
        role_service, query_service, stats_service, athlete_id
    )
    history_text = build_history_table(summary.history)
    pb_text = build_pb_table(summary.pb_rows)
    header = (
        f"{t('admin.debug.badge')}\n<b>{summary.full_name}</b> (ID {summary.athlete_id})\n"
        f"{t('admin.browser.weekly_summary', attempts=summary.weekly_attempts, prs=summary.weekly_prs)}"
    )
    await cb.message.answer(
        f"{header}\n\n{pb_text}\n\n{history_text}", parse_mode="HTML"
    )

    grouped = group_history(summary.history)
    chart = render_progress_chart(grouped)
    if chart:
        document = BufferedInputFile(
            chart, filename=f"athlete_{summary.athlete_id}_progress.png"
        )
        await cb.message.answer_photo(
            document, caption=t("admin.browser.chart.caption")
        )


__all__ = [
    "router",
    "DEBUG_BROWSE_CALLBACK",
    "SELECT_CALLBACK_PREFIX",
    "get_admin_summary",
    "build_history_table",
    "build_pb_table",
    "group_history",
    "render_progress_chart",
]
