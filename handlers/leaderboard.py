from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from services.stats_service import StatsPeriod, StatsService
from utils import fmt_time

router = Router()

LEADERBOARD_LIMIT = 10

PERIOD_TITLES = {
    StatsPeriod.WEEK: "недели",
    StatsPeriod.MONTH: "месяца",
}

STROKE_LABELS = {
    "freestyle": "кроль",
    "backstroke": "спина",
    "butterfly": "батерфляй",
    "breaststroke": "брас",
    "medley": "комплекс",
}


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
        await message.answer("Используй: /leaders week или /leaders month")
        return

    progress_msg = await message.answer("⏳ Считаю рейтинг…")
    entries = await stats_service.leaderboard(period, limit=LEADERBOARD_LIMIT)
    if not entries:
        await progress_msg.edit_text("Пока нет улучшений за выбранный период.")
        return

    title = PERIOD_TITLES.get(period, period.value)
    lines = [f"🏆 Лидеры {title}:"]
    for idx, entry in enumerate(entries, start=1):
        lines.append(
            f"{idx}. {entry.athlete_name} — {entry.pr_count} PR, {entry.attempts} попыток"
        )
    await progress_msg.edit_text("\n".join(lines))


@router.message(Command("my_progress_week"))
async def my_progress_week(message: types.Message, stats_service: StatsService) -> None:
    user = message.from_user
    if user is None:
        await message.answer("Не удалось определить профиль пользователя.")
        return

    progress_msg = await message.answer("⏳ Сканирую твою неделю…")
    summary = await stats_service.weekly_progress(user.id)
    if summary.attempts == 0:
        await progress_msg.edit_text("За 7 дней попыток не найдено. Пора в бассейн! 💪")
        return

    lines = [
        "📊 Итоги недели:",
        f"Попытки: {summary.attempts}",
        f"PR: {summary.pr_count}",
    ]

    if summary.highlights:
        lines.append("🔥 Лучшие заплывы:")
        for result in summary.highlights:
            prefix = "⭐" if result.is_pr else "•"
            stroke_label = STROKE_LABELS.get(result.stroke, result.stroke)
            lines.append(
                f"{prefix} {result.distance} м {stroke_label} — {fmt_time(result.total_seconds)}"
            )
    else:
        lines.append("Пока без выдающихся результатов.")

    await progress_msg.edit_text("\n".join(lines))
