from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Iterable, Sequence

from aiogram import Bot

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
        total: float,
        timestamp: str,
        new_prs: Sequence[tuple[int, float]] | None = None,
    ) -> None:
        """Broadcast information about a freshly logged sprint result."""

        recipients = await self._get_subscribers(exclude={actor_id})
        if not recipients:
            return

        logger.info(
            "Broadcasting result update for athlete %s to %s subscribers",
            athlete_id,
            len(recipients),
        )

        parts = [
            "🏁 <b>Новий результат у спринті!</b>",
            f"Спортсмен {athlete_name} подолав {dist} м за {fmt_time(total)}.",
            f"Середня швидкість {speed(dist, total):.2f} м/с.",
            f"Додано {timestamp} тренером {actor_name}.",
        ]
        if new_prs:
            prs = ", ".join(f"#{idx + 1} — {fmt_time(value)}" for idx, value in new_prs)
            parts.append(f"🥳 Нові PR сегментів: {prs}")

        await self._broadcast("\n".join(parts), recipients)

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
