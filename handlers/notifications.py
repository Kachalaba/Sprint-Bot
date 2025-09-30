from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from notifications import NotificationService

router = Router()


@router.message(Command("notify_on"))
async def enable_notifications(
    message: types.Message, notifications: NotificationService
) -> None:
    """Enable scheduled and instant notifications for the chat."""

    subscribed = await notifications.subscribe(message.chat.id)
    if subscribed:
        text = (
            "🔔 Сповіщення активовані!\n"
            "Ви отримаєте нагадування про нові спринти та оновлення результатів."
        )
    else:
        text = "🔔 Сповіщення вже були увімкнені."
    await message.answer(text)


@router.message(Command("notify_off"))
async def disable_notifications(
    message: types.Message, notifications: NotificationService
) -> None:
    """Disable all notifications for the chat."""

    removed = await notifications.unsubscribe(message.chat.id)
    if removed:
        text = "🔕 Сповіщення вимкнені. Ви завжди можете знову активувати їх командою /notify_on."
    else:
        text = "🔕 Наразі сповіщення вже вимкнені."
    await message.answer(text)


@router.message(Command("notify_info"))
async def notification_info(
    message: types.Message, notifications: NotificationService
) -> None:
    """Share current notification settings and schedule details."""

    subscribed = await notifications.is_subscribed(message.chat.id)
    status = "увімкнено ✅" if subscribed else "вимкнено ❌"

    schedule = notifications.describe_schedule()
    next_run = notifications.next_sprint_run()
    weekday = notifications.weekday_name(next_run.weekday())
    next_label = f"{weekday}, {next_run:%d.%m о %H:%M}"

    text = (
        "<b>Нагадування SprintBot</b>\n"
        f"Статус: {status}\n"
        f"{schedule}\n"
        f"Найближче нагадування: {next_label}.\n\n"
        "Команди:\n"
        "• /notify_on — увімкнути сповіщення\n"
        "• /notify_off — вимкнути сповіщення"
    )
    await message.answer(text)
