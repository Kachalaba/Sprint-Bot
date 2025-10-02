from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Iterable, Mapping, Sequence

from aiogram import Bot

from i18n import t
from utils import fmt_time, speed

logger = logging.getLogger(__name__)

WEEKDAY_NAMES: Sequence[str] = (
    "Понеділок",
    "Вівторок",
    "Середа",
    "Четвер",
    "Пʼятниця",
    "Субота",
    "Неділя",
)


@dataclass(frozen=True)
class SprintReminderPlan:
    """Describe when to send automated sprint reminders."""

    weekdays: tuple[int, ...]
    time_of_day: time
    message_template: str = (
        "⏱ <b>Нагадування про спринт</b>\n"
        "Новий сет стартує {start_label}. Підготуйтеся до тренування та оновіть результати!"
    )


class NotificationService:
    """Manage scheduled reminders and push notifications for the bot."""

    def __init__(
        self,
        bot: Bot,
        sprint_plan: SprintReminderPlan | None = None,
    ) -> None:
        self.bot = bot
        self.sprint_plan = sprint_plan or SprintReminderPlan(
            weekdays=(0, 2, 4),
            time_of_day=time(hour=9, minute=0),
        )
        self._subscribers: set[int] = set()
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    async def startup(self) -> None:
        """Launch background workers once dispatcher starts polling."""

        self._cleanup_finished_tasks()
        if any(not task.done() for task in self._tasks):
            return

        reminder_task = asyncio.create_task(
            self._sprint_reminder_loop(), name="sprint-reminder-loop"
        )
        reminder_task.add_done_callback(self._tasks.discard)
        self._tasks.add(reminder_task)
        logger.info(
            "Notification service started. Active subscribers: %s",
            len(self._subscribers),
        )

    async def shutdown(self) -> None:
        """Stop background workers gracefully when dispatcher shuts down."""

        while self._tasks:
            task = self._tasks.pop()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug("Cancelled task %s", task.get_name())

        logger.info("Notification service stopped.")

    async def subscribe(self, chat_id: int) -> bool:
        """Subscribe chat to receive notifications."""

        async with self._lock:
            if chat_id in self._subscribers:
                return False
            self._subscribers.add(chat_id)
            logger.info("Chat %s subscribed to notifications", chat_id)
            return True

    async def unsubscribe(self, chat_id: int) -> bool:
        """Remove chat from the notification list."""

        async with self._lock:
            if chat_id not in self._subscribers:
                return False
            self._subscribers.remove(chat_id)
            logger.info("Chat %s unsubscribed from notifications", chat_id)
            return True

    async def is_subscribed(self, chat_id: int) -> bool:
        """Return True if chat has notifications enabled."""

        async with self._lock:
            return chat_id in self._subscribers

    async def notify_new_result(
        self,
        *,
        actor_id: int,
        actor_name: str,
        athlete_id: int,
        athlete_name: str,
        dist: int,
        stroke: str,
        total: float,
        timestamp: str,
        stats: Mapping[str, Any] | None = None,
        trainers: Sequence[int] | None = None,
        new_prs: Sequence[tuple[int, float]] | None = None,
    ) -> None:
        """Broadcast information about a freshly logged sprint result."""

        stats = stats or {}
        segment_flags = list(stats.get("segment_prs") or [])
        sob_delta = float(stats.get("sob_delta") or 0.0)
        total_pr_delta = float(stats.get("total_pr_delta") or 0.0)
        new_total_pr = bool(stats.get("new_total_pr"))
        has_segment_pr = bool(new_prs) or any(segment_flags)
        has_pr = new_total_pr or has_segment_pr or sob_delta > 0.0

        recipients = await self._get_subscribers(exclude={actor_id})
        if recipients:
            logger.info(
                "Broadcasting result update for athlete %s to %s subscribers",
                athlete_id,
                len(recipients),
            )

            message = self._build_broadcast_message(
                athlete_name=athlete_name,
                stroke=stroke,
                dist=dist,
                total=total,
                timestamp=timestamp,
                actor_name=actor_name,
                new_total_pr=new_total_pr,
                total_pr_delta=total_pr_delta,
                new_prs=new_prs,
                sob_delta=sob_delta,
                sob_current=stats.get("sob_current"),
            )

            await self._broadcast(message, recipients)

        if not has_pr:
            return

        target_ids = set(trainers or ())
        target_ids.add(athlete_id)
        target_ids.discard(actor_id)
        if not target_ids:
            return

        summary_text = self._build_pr_summary(
            athlete_name=athlete_name,
            stroke=stroke,
            dist=dist,
            total=total,
            new_total_pr=new_total_pr,
            total_pr_delta=total_pr_delta,
            new_prs=new_prs,
            has_segment_pr=has_segment_pr,
            segment_flags=segment_flags,
            sob_delta=sob_delta,
            sob_current=stats.get("sob_current"),
        )
        for chat_id in target_ids:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=summary_text,
                    parse_mode="HTML",
                )
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning(
                    "Failed to deliver PR notification to %s: %s",
                    chat_id,
                    exc,
                    exc_info=True,
                )

    async def broadcast_text(
        self, text: str, *, exclude: Iterable[int] | None = None
    ) -> None:
        """Send arbitrary text to every subscriber."""

        recipients = await self._get_subscribers(exclude=set(exclude or ()))
        if not recipients:
            return
        await self._broadcast(text, recipients)

    def describe_schedule(self) -> str:
        """Return human readable description of the sprint reminder plan."""

        weekdays = ", ".join(
            self.weekday_name(day) for day in sorted(self.sprint_plan.weekdays)
        )
        time_label = self.sprint_plan.time_of_day.strftime("%H:%M")
        return f"Нагадування надходять о {time_label} у дні: {weekdays}."

    def next_sprint_run(self, *, now: datetime | None = None) -> datetime:
        """Return next datetime when the sprint reminder will be sent."""

        return self._next_sprint_run(now or datetime.now())

    def weekday_name(self, weekday: int) -> str:
        """Return localized weekday name for given index."""

        return WEEKDAY_NAMES[weekday % 7]

    async def _get_subscribers(
        self, *, exclude: Iterable[int] | None = None
    ) -> set[int]:
        exclude_set = set(exclude or ())
        async with self._lock:
            return {cid for cid in self._subscribers if cid not in exclude_set}

    async def _broadcast(self, text: str, recipients: Iterable[int]) -> None:
        """Send prepared text to provided chat ids with error handling."""

        for chat_id in recipients:
            try:
                await self.bot.send_message(chat_id=chat_id, text=text)
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning(
                    "Failed to deliver notification to %s: %s",
                    chat_id,
                    exc,
                    exc_info=True,
                )

    def _cleanup_finished_tasks(self) -> None:
        self._tasks = {task for task in self._tasks if not task.done()}

    async def _sprint_reminder_loop(self) -> None:
        """Background loop sending sprint reminders according to the plan."""

        try:
            while True:
                now = datetime.now()
                next_run = self._next_sprint_run(now)
                delay = max(0.0, (next_run - now).total_seconds())
                await asyncio.sleep(delay)

                recipients = await self._get_subscribers()
                if not recipients:
                    logger.debug(
                        "Skipping sprint reminder %s — no active subscribers.", next_run
                    )
                    continue

                start_label = self._format_start_label(next_run)
                message = self.sprint_plan.message_template.format(
                    start_label=start_label
                )
                await self._broadcast(message, recipients)
        except asyncio.CancelledError:  # pragma: no cover - cooperative cancellation
            logger.debug("Sprint reminder loop cancelled")
            raise

    def _next_sprint_run(self, start: datetime) -> datetime:
        plan = self.sprint_plan
        for offset in range(0, 8):
            candidate_date = (start + timedelta(days=offset)).date()
            candidate_dt = datetime.combine(candidate_date, plan.time_of_day)
            if candidate_dt <= start:
                continue
            if candidate_dt.weekday() in plan.weekdays:
                return candidate_dt

        min_weekday = min(plan.weekdays)
        days_ahead = (7 - start.weekday() + min_weekday) % 7 or 7
        candidate_date = (start + timedelta(days=days_ahead)).date()
        return datetime.combine(candidate_date, plan.time_of_day)

    def _format_start_label(self, start: datetime) -> str:
        weekday = self.weekday_name(start.weekday())
        return f"{weekday}, {start:%d.%m о %H:%M}"

    def quiet_hours_notice(self, *, lang: str | None = None) -> str:
        """Return localized notice about quiet hours."""

        return t("note.quiet_hours", lang=lang)

    def info_notice(self, *, lang: str | None = None) -> str:
        """Return localized informational notice."""

        return t("note.info", lang=lang)

    def _build_broadcast_message(
        self,
        *,
        athlete_name: str,
        stroke: str,
        dist: int,
        total: float,
        timestamp: str,
        actor_name: str,
        new_total_pr: bool,
        total_pr_delta: float,
        new_prs: Sequence[tuple[int, float]] | None,
        sob_delta: float,
        sob_current: float | str | None,
        lang: str | None = None,
    ) -> str:
        """Compose localized broadcast message for a new result."""

        parts = [
            t("note.result_header", lang=lang),
            t(
                "note.result_body",
                lang=lang,
                athlete=athlete_name,
                stroke=stroke,
                distance=dist,
                time=fmt_time(total),
            ),
            t(
                "note.result_speed",
                lang=lang,
                speed=f"{speed(dist, total):.2f}",
            ),
            t(
                "note.result_added",
                lang=lang,
                timestamp=timestamp,
                coach=actor_name,
            ),
        ]
        if new_total_pr:
            delta_suffix = self._format_total_pr_delta(total_pr_delta)
            parts.append(
                t(
                    "note.result_total_pr",
                    lang=lang,
                    delta=delta_suffix,
                )
            )
        if new_prs:
            segment_labels = ", ".join(
                t("note.pr_segment", lang=lang, seg=idx + 1, time=fmt_time(value))
                for idx, value in new_prs
            )
            parts.append(t("note.result_segment_prs", lang=lang, items=segment_labels))
        if sob_delta > 0:
            current_suffix = self._format_sob_suffix(sob_current, lang=lang)
            parts.append(
                t(
                    "note.result_sob",
                    lang=lang,
                    delta=f"{sob_delta:.2f}",
                    current=current_suffix,
                )
            )

        return "\n".join(parts)

    def _build_pr_summary(
        self,
        *,
        athlete_name: str,
        stroke: str,
        dist: int,
        total: float,
        new_total_pr: bool,
        total_pr_delta: float,
        new_prs: Sequence[tuple[int, float]] | None,
        has_segment_pr: bool,
        segment_flags: Sequence[bool],
        sob_delta: float,
        sob_current: float | str | None,
        lang: str | None = None,
    ) -> str:
        """Compose localized summary for PR recipients."""

        parts = [
            t("note.pr_title", lang=lang),
            t(
                "note.pr_athlete",
                lang=lang,
                athlete=athlete_name,
                stroke=stroke,
                distance=dist,
            ),
        ]
        if new_total_pr:
            delta_suffix = self._format_total_pr_delta(total_pr_delta)
            parts.append(
                t(
                    "note.pr_total",
                    lang=lang,
                    time=fmt_time(total),
                    delta=delta_suffix,
                )
            )
        if new_prs:
            items = ", ".join(
                t("note.pr_segment", lang=lang, seg=idx + 1, time=fmt_time(value))
                for idx, value in new_prs
            )
            parts.append(t("note.pr_segments", lang=lang, items=items))
        elif has_segment_pr:
            improved = [
                t("note.pr_segment_short", lang=lang, seg=idx + 1)
                for idx, flag in enumerate(segment_flags)
                if flag
            ]
            if improved:
                parts.append(
                    t(
                        "note.pr_segments",
                        lang=lang,
                        items=", ".join(improved),
                    )
                )
        if sob_delta > 0:
            current_suffix = self._format_sob_suffix(sob_current, lang=lang)
            parts.append(
                t(
                    "note.sob_delta",
                    lang=lang,
                    delta=f"{sob_delta:.2f}",
                    current=current_suffix,
                )
            )

        return "\n".join(parts)

    def _format_total_pr_delta(self, total_pr_delta: float) -> str:
        """Return formatted delta suffix for total PR notifications."""

        if total_pr_delta:
            return f" (−{total_pr_delta:.2f} с)"
        return ""

    def _format_sob_suffix(
        self, sob_current: float | str | None, *, lang: str | None = None
    ) -> str:
        """Return localized suffix for Sum of Best notifications."""

        if sob_current is None:
            return ""
        try:
            current_value = float(sob_current)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return ""
        return t(
            "note.sob_current",
            lang=lang,
            current=fmt_time(current_value),
        )
