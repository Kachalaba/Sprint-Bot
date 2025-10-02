from __future__ import annotations

from typing import Sequence

from aiogram import Router, types
from aiogram.filters import Command

from i18n import t
from services.stats_service import (
    LeaderboardEntry,
    StatsPeriod,
    StatsService,
    WeeklyProgress,
)
from utils import fmt_time

router = Router()

LEADERBOARD_LIMIT = 10

_LEADERBOARD_TITLE_KEYS = {
    StatsPeriod.WEEK: "lead.title.week",
    StatsPeriod.MONTH: "lead.title.month",
}

_STROKE_TITLE_KEYS = {
    "freestyle": "lead.stroke.freestyle",
    "backstroke": "lead.stroke.backstroke",
    "butterfly": "lead.stroke.butterfly",
    "breaststroke": "lead.stroke.breaststroke",
    "medley": "lead.stroke.medley",
}


def _resolve_stroke_label(stroke: str) -> str:
    key = _STROKE_TITLE_KEYS.get(stroke)
    if key is None:
        return stroke
    return t(key)


def build_leaderboard_lines(
    entries: Sequence[LeaderboardEntry], period: StatsPeriod
) -> list[str]:
    title_key = _LEADERBOARD_TITLE_KEYS.get(period)
    if title_key:
        lines = [t(title_key)]
    else:  # pragma: no cover - defensive branch for unexpected period
        lines = [t("lead.title.generic", period=period.value)]
    for idx, entry in enumerate(entries, start=1):
        value = t("lead.value", pr=entry.pr_count, attempts=entry.attempts)
        lines.append(t("lead.item", place=idx, user=entry.athlete_name, value=value))
    return lines


def build_weekly_progress_lines(summary: WeeklyProgress) -> list[str]:
    lines = [
        t("lead.my_week.title"),
        t("lead.my_week.attempts", value=summary.attempts),
        t("lead.my_week.pr", value=summary.pr_count),
    ]
    if summary.highlights:
        lines.append(t("lead.my_week.highlights_title"))
        for result in summary.highlights:
            mark = "⭐" if result.is_pr else "•"
            stroke_label = _resolve_stroke_label(result.stroke)
            lines.append(
                t(
                    "lead.my_week.highlight_item",
                    mark=mark,
                    distance=result.distance,
                    stroke=stroke_label,
                    time=fmt_time(result.total_seconds),
                )
            )
    else:
        lines.append(t("lead.my_week.no_highlights"))
    return lines


def _parse_period(message: types.Message) -> StatsPeriod | None:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    raw = parts[1].strip().lower()
    if raw == StatsPeriod.WEEK.value:
        return StatsPeriod.WEEK
    if raw == StatsPeriod.MONTH.value:
        return StatsPeriod.MONTH
    return None


@router.message(Command("leaders"))
async def show_leaders(message: types.Message, stats_service: StatsService) -> None:
    period = _parse_period(message)
    if period is None:
        await message.answer(t("lead.usage"))
        return

    progress_msg = await message.answer(t("lead.loading"))
    entries = await stats_service.leaderboard(period, limit=LEADERBOARD_LIMIT)
    if not entries:
        await progress_msg.edit_text(t("lead.empty"))
        return

    lines = build_leaderboard_lines(entries, period)
    await progress_msg.edit_text("\n".join(lines))


@router.message(Command("my_progress_week"))
async def my_progress_week(message: types.Message, stats_service: StatsService) -> None:
    user = message.from_user
    if user is None:
        await message.answer(t("lead.my_week.user_missing"))
        return

    progress_msg = await message.answer(t("lead.my_week.loading"))
    summary = await stats_service.weekly_progress(user.id)
    if summary.attempts == 0:
        await progress_msg.edit_text(t("lead.my_week.empty"))
        return

    lines = build_weekly_progress_lines(summary)
    await progress_msg.edit_text("\n".join(lines))
