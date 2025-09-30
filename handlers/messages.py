"""Handlers for coach-athlete chat interactions."""

from __future__ import annotations

import logging
from datetime import datetime
from html import escape

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from chat_service import ChatService
from services import ADMIN_IDS, get_athlete_name, get_registered_athletes

logger = logging.getLogger(__name__)

router = Router()

ROLE_TRAINER = "trainer"
ROLE_ATHLETE = "athlete"


class ChatStates(StatesGroup):
    """FSM state describing ongoing dialog typing."""

    writing = State()


def _user(event: types.Message | types.CallbackQuery) -> types.User:
    return event.from_user if isinstance(event, types.Message) else event.from_user


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


def _thread_line(title: str, summary: dict) -> str:
    preview = (summary.get("last_text") or "(без тексту)")[:80]
    stamp = datetime.fromisoformat(summary["last_at"]).strftime("%d.%m %H:%M")
    unread = (
        f" — <b>{summary.get('unread', 0)} нових</b>" if summary.get("unread") else ""
    )
    return f"• {escape(title)} ({stamp}){unread}\n  {escape(preview)}"


def _dialog_keyboard(role: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад до списку", callback_data=f"chat:{role}:back"
                )
            ]
        ]
    )


def _athlete_label(athlete_id: int) -> str:
    return get_athlete_name(athlete_id) or f"ID {athlete_id}"


async def _trainer_label(trainer_id: int, bot: Bot | None) -> str:
    if bot is None:
        return f"Тренер {trainer_id}"
    try:
        chat = await bot.get_chat(trainer_id)
    except Exception:  # pragma: no cover - network interaction
        return f"Тренер {trainer_id}"
    return chat.full_name or f"Тренер {trainer_id}"


@router.message(Command("messages"))
async def cmd_messages(
    message: types.Message,
    state: FSMContext,
    chat_service: ChatService,
) -> None:
    """Open messaging menu via command."""

    await state.clear()
    await _show_menu(event=message, chat_service=chat_service)


@router.callback_query(F.data == "menu_messages")
async def menu_messages(
    cb: types.CallbackQuery,
    state: FSMContext,
    chat_service: ChatService,
) -> None:
    """Open messaging menu via inline keyboard."""

    await state.clear()
    await _show_menu(event=cb, chat_service=chat_service)


async def _show_menu(
    *,
    event: types.Message | types.CallbackQuery,
    chat_service: ChatService,
) -> None:
    user = _user(event)
    role = ROLE_TRAINER if str(user.id) in ADMIN_IDS else ROLE_ATHLETE
    await _show_threads(event=event, chat_service=chat_service, role=role)


def _button_label(title_fn, summary: dict) -> str:
    title = title_fn(summary["counterpart"])
    unread = summary.get("unread", 0)
    return f"{title} ({unread} нових)" if unread else title


async def _show_threads(
    *,
    event: types.Message | types.CallbackQuery,
    chat_service: ChatService,
    role: str,
) -> None:
    user_id = _user(event).id
    threads = await chat_service.list_threads(role=role, user_id=user_id)
    if role == ROLE_TRAINER:
        title_fn = _athlete_label
        header = "<b>Повідомлення спортсменам</b>"
        empty_hint = "Оберіть спортсмена, щоб надіслати перше повідомлення."
        fallback = "Немає зареєстрованих спортсменів для переписки."
        athletes = get_registered_athletes()
    else:
        title_fn = lambda value: f"Тренер {value}"
        header = "<b>Ваші тренери</b>"
        empty_hint = "Поки що немає повідомлень від тренера."
        fallback = empty_hint
        athletes = []

    lines = [header]
    for item in threads:
        lines.append(_thread_line(title_fn(item["counterpart"]), item))

    if not threads:
        lines.append(empty_hint if (athletes or role == ROLE_ATHLETE) else fallback)

    buttons = [
        [
            InlineKeyboardButton(
                text=_button_label(title_fn, item),
                callback_data=f"chat:{role}:dialog:{item['counterpart']}",
            )
        ]
        for item in threads
    ]

    if role == ROLE_TRAINER and athletes:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✉️ Написати спортсмену", callback_data="chat:trainer:choose"
                )
            ]
        )

    markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await _answer(event, "\n".join(lines), reply_markup=markup)


def _parse_callback(data: str) -> tuple[str, str, str | None]:
    parts = data.split(":", 3)
    role = parts[1] if len(parts) > 1 else ""
    action = parts[2] if len(parts) > 2 else ""
    value = parts[3] if len(parts) > 3 else None
    return role, action, value


@router.callback_query(F.data.startswith("chat:"))
async def chat_callbacks(
    cb: types.CallbackQuery,
    state: FSMContext,
    chat_service: ChatService,
    bot: Bot,
) -> None:
    """Handle inline button actions inside chat menu."""

    role, action, value = _parse_callback(cb.data)
    if role not in {ROLE_TRAINER, ROLE_ATHLETE}:
        await cb.answer("Невідома дія.", show_alert=True)
        return

    if action == "back":
        await state.clear()
        await _show_threads(event=cb, chat_service=chat_service, role=role)
        return

    if role == ROLE_TRAINER and action == "choose":
        await _show_athlete_picker(cb)
        return

    if action == "dialog" and value is not None:
        try:
            counterpart = int(value)
        except ValueError:
            await cb.answer("Некоректний ідентифікатор.", show_alert=True)
            return
        trainer_id, athlete_id = (
            (_user(cb).id, counterpart)
            if role == ROLE_TRAINER
            else (counterpart, _user(cb).id)
        )
        await _show_dialog(
            event=cb,
            role=role,
            trainer_id=trainer_id,
            athlete_id=athlete_id,
            chat_service=chat_service,
            state=state,
            bot=bot,
        )
        return

    await cb.answer("Дія тимчасово недоступна.", show_alert=True)


async def _show_athlete_picker(cb: types.CallbackQuery) -> None:
    athletes = get_registered_athletes()
    if not athletes:
        await _answer(
            cb, "Список спортсменів порожній. Спочатку зареєструйте спортсменів."
        )
        return

    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []
    for athlete_id, name in athletes:
        current.append(
            InlineKeyboardButton(
                text=name, callback_data=f"chat:trainer:dialog:{athlete_id}"
            )
        )
        if len(current) == 2:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="chat:trainer:back")]
    )
    await _answer(
        cb,
        "Оберіть спортсмена для нового повідомлення:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _show_dialog(
    *,
    event: types.Message | types.CallbackQuery,
    role: str,
    trainer_id: int,
    athlete_id: int,
    chat_service: ChatService,
    state: FSMContext,
    bot: Bot,
    notice: str | None = None,
) -> None:
    if role == ROLE_TRAINER:
        await chat_service.mark_read(
            role=ROLE_TRAINER, trainer_id=trainer_id, athlete_id=athlete_id
        )
        counterpart = _athlete_label(athlete_id)
    else:
        await chat_service.mark_read(
            role=ROLE_ATHLETE, trainer_id=trainer_id, athlete_id=athlete_id
        )
        counterpart = await _trainer_label(trainer_id, bot)

    history = await chat_service.fetch_dialog(
        trainer_id=trainer_id,
        athlete_id=athlete_id,
        limit=20,
    )
    text_lines = [f"<b>Чат з {escape(counterpart)}</b>"]
    if notice:
        text_lines.append(escape(notice))
    if history:
        for item in history:
            text_lines.append(_format_message(item))
    else:
        text_lines.append("Поки що немає повідомлень. Напишіть перше!")

    await _answer(event, "\n\n".join(text_lines), reply_markup=_dialog_keyboard(role))
    await state.set_state(ChatStates.writing)
    await state.update_data(role=role, trainer_id=trainer_id, athlete_id=athlete_id)


def _format_message(message: dict) -> str:
    author = "👨‍🏫 Тренер" if message["sender_role"] == ROLE_TRAINER else "🏊 Спортсмен"
    stamp = datetime.fromisoformat(message["created_at"]).strftime("%d.%m %H:%M")
    return f"{author} ({stamp})\n{escape(message['text'])}"


@router.message(ChatStates.writing)
async def process_text(
    message: types.Message,
    state: FSMContext,
    chat_service: ChatService,
    bot: Bot,
) -> None:
    """Save new message and refresh dialog."""

    if not message.text:
        await message.answer("Надішліть, будь ласка, текстове повідомлення.")
        return

    data = await state.get_data()
    role = data.get("role")
    trainer_id = data.get("trainer_id")
    athlete_id = data.get("athlete_id")
    if (
        role not in {ROLE_TRAINER, ROLE_ATHLETE}
        or trainer_id is None
        or athlete_id is None
    ):
        await state.clear()
        await message.answer("Сесію переписки скинуто. Відкрийте діалог знову.")
        return

    text = message.text.strip()
    await chat_service.add_message(
        trainer_id=trainer_id,
        athlete_id=athlete_id,
        sender_role=role,
        text=text,
    )

    if role == ROLE_TRAINER:
        sender_name = message.from_user.full_name or "Тренер"
        body = (
            f"💬 Нове повідомлення від тренера {escape(sender_name)}:\n\n"
            f"{escape(text)}"
        )
        target_id = athlete_id
    else:
        sender_name = (
            get_athlete_name(athlete_id) or message.from_user.full_name or "Спортсмен"
        )
        body = (
            f"💬 Нове повідомлення від спортсмена {escape(sender_name)}:\n\n"
            f"{escape(text)}"
        )
        target_id = trainer_id

    try:
        await bot.send_message(chat_id=target_id, text=body)
    except Exception as exc:  # pragma: no cover - network interaction
        logger.warning("Failed to deliver chat notification to %s: %s", target_id, exc)

    await _show_dialog(
        event=message,
        role=role,
        trainer_id=trainer_id,
        athlete_id=athlete_id,
        chat_service=chat_service,
        state=state,
        bot=bot,
        notice="Повідомлення надіслано ✅",
    )
