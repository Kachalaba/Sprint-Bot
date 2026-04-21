from __future__ import annotations

from datetime import datetime
from time import perf_counter
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Router, types
from aiogram.filters import Command

from i18n import t
from notifications import QUIET_HOURS_WINDOW, NotificationService, is_quiet_now
from sprint_bot.config import get_settings
from utils.logger import get_logger

router = Router()
logger = get_logger(__name__)


@router.message(Command("notify_on"))
async def enable_notifications(
    message: types.Message, notifications: NotificationService
) -> None:
    """Enable scheduled and instant notifications for the chat."""

    command = "/notify_on"
    user = message.from_user
    user_id = user.id if user else message.chat.id
    started = perf_counter()
    logger.info(
        "notify_on_start",
        extra={"user_id": user_id, "cmd": command, "latency_ms": None},
    )
    subscribed = await notifications.subscribe(message.chat.id)
    if subscribed:
        text = (
            "🔔 Сповіщення активовані!\n"
            "Ви отримаєте нагадування про нові спринти та оновлення результатів."
        )
    else:
        text = "🔔 Сповіщення вже були увімкнені."
    await message.answer(text)
    latency_ms = (perf_counter() - started) * 1000
    logger.info(
        "notify_on_complete",
        extra={
            "user_id": user_id,
            "cmd": command,
            "latency_ms": round(latency_ms, 2),
        },
    )


@router.message(Command("notify_off"))
async def disable_notifications(
    message: types.Message, notifications: NotificationService
) -> None:
    """Disable all notifications for the chat."""

    command = "/notify_off"
    user = message.from_user
    user_id = user.id if user else message.chat.id
    started = perf_counter()
    logger.info(
        "notify_off_start",
        extra={"user_id": user_id, "cmd": command, "latency_ms": None},
    )
    removed = await notifications.unsubscribe(message.chat.id)
    if removed:
        text = "🔕 Сповіщення вимкнені. Ви завжди можете знову активувати їх командою /notify_on."
    else:
        text = "🔕 Наразі сповіщення вже вимкнені."
    await message.answer(text)
    latency_ms = (perf_counter() - started) * 1000
    logger.info(
        "notify_off_complete",
        extra={
            "user_id": user_id,
            "cmd": command,
            "latency_ms": round(latency_ms, 2),
        },
    )


def _resolve_timezone() -> tuple[str, ZoneInfo]:
    tz_name = get_settings().quiet_hours_tz
    try:
        return tz_name, ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        fallback = "UTC"
        return fallback, ZoneInfo(fallback)


def _format_quiet_window() -> str:
    if QUIET_HOURS_WINDOW is None:
        return t("note.info_quiet_disabled")
    start, end = QUIET_HOURS_WINDOW
    return t(
        "note.info_quiet_enabled",
        start=start.strftime("%H:%M"),
        end=end.strftime("%H:%M"),
    )


@router.message(Command("notify_info"))
async def notification_info(
    message: types.Message, notifications: NotificationService
) -> None:
    """Share current notification settings, quiet hours, and subscription status."""

    command = "/notify_info"
    user = message.from_user
    user_id = user.id if user else message.chat.id
    started = perf_counter()
    logger.info(
        "notify_info_start",
        extra={"user_id": user_id, "cmd": command, "latency_ms": None},
    )
    tz_name, tzinfo = _resolve_timezone()
    now_local = datetime.now(tzinfo)
    quiet_now = await is_quiet_now(tz=tz_name)

    quiet_state_key = "note.info_state_quiet" if quiet_now else "note.info_state_active"
    quiet_state = t(quiet_state_key)

    try:
        subscribed = await notifications.is_subscribed(message.chat.id)
    except AttributeError:
        subscription_key = "note.info_subscription_always"
    else:
        subscription_key = (
            "note.info_subscription_on" if subscribed else "note.info_subscription_off"
        )
    subscription_status = t(subscription_key)

    text = t(
        "note.info",
        quiet_window=_format_quiet_window(),
        local_time=f"{now_local:%H:%M} ({tz_name})",
        quiet_state=quiet_state,
        subscription=subscription_status,
    )
    await message.answer(text)
    latency_ms = (perf_counter() - started) * 1000
    logger.info(
        "notify_info_complete",
        extra={
            "user_id": user_id,
            "cmd": command,
            "latency_ms": round(latency_ms, 2),
        },
    )
