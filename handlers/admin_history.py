from __future__ import annotations

import json
from datetime import datetime
from html import escape
from typing import Any, Iterable

from aiogram import Router, types
from aiogram.filters import Command

from keyboards import AuditUndoCB, build_audit_entry_keyboard
from role_service import ROLE_ADMIN, ROLE_TRAINER
from services.audit_service import AuditEntry, AuditService
from utils.roles import require_roles

router = Router()

_ACTION_LABELS: dict[str, str] = {
    "create": "створено",
    "update": "оновлено",
    "delete": "видалено",
}

_ENTITY_LABELS: dict[str, str] = {
    "result": "Результат",
    "template": "Шаблон",
}

_DEFAULT_LIMIT = 10


@router.message(Command("history"), require_roles(ROLE_ADMIN, ROLE_TRAINER))
async def cmd_history(
    message: types.Message,
    audit_service: AuditService,
) -> None:
    """Show recent audit entries for admins and coaches."""

    limit, user_filter, error = _parse_arguments(message.text or "")
    if error:
        await message.answer(error)
        return

    entries = await audit_service.list_entries(limit=limit, user_id=user_filter)
    if not entries:
        await message.answer("Поки немає записів аудиту.")
        return

    for entry in entries:
        text = _format_entry(entry)
        await message.answer(
            text,
            reply_markup=build_audit_entry_keyboard(entry.id),
            parse_mode="HTML",
        )


@router.callback_query(AuditUndoCB.filter(), require_roles(ROLE_ADMIN, ROLE_TRAINER))
async def handle_undo(
    callback: types.CallbackQuery,
    callback_data: AuditUndoCB,
    audit_service: AuditService,
) -> None:
    """Undo audit operation when requested from inline button."""

    success = await audit_service.undo(callback_data.op_id)
    if not success:
        await callback.answer("Не вдалося виконати відкат.", show_alert=True)
        return
    await callback.answer("Відкат виконано.")
    if callback.message:
        await callback.message.answer(
            f"✅ Операцію #{callback_data.op_id} відкотили."
        )


def _parse_arguments(text: str) -> tuple[int, int | None, str | None]:
    parts = text.strip().split()
    if len(parts) < 2:
        return _DEFAULT_LIMIT, None, None
    keyword = parts[1].lower()
    if keyword == "last":
        if len(parts) < 3:
            return _DEFAULT_LIMIT, None, "Вкажіть кількість записів: /history last 5"
        try:
            limit = max(1, min(20, int(parts[2])))
        except ValueError:
            return _DEFAULT_LIMIT, None, "Кількість має бути числом."
        return limit, None, None
    if keyword == "user":
        if len(parts) < 3:
            return _DEFAULT_LIMIT, None, "Вкажіть ID користувача: /history user 123"
        try:
            user_id = int(parts[2])
        except ValueError:
            return _DEFAULT_LIMIT, None, "ID користувача має бути числом."
        return _DEFAULT_LIMIT, user_id, None
    return _DEFAULT_LIMIT, None, "Невідомий параметр. Використовуйте user або last."


def _format_entry(entry: AuditEntry) -> str:
    header = (
        f"#{entry.id} • {entry.ts.strftime('%Y-%m-%d %H:%M:%S')} • "
        f"👤 <code>{entry.user_id}</code>"
    )
    entity_label = _ENTITY_LABELS.get(entry.entity_type, entry.entity_type.title())
    action_label = _ACTION_LABELS.get(entry.action, entry.action)
    body = (
        f"{entity_label} <code>{escape(entry.entity_id)}</code> — {action_label}"
    )
    sections: list[str] = [header, body]
    if entry.action == "create":
        sections.extend(_format_section("Стало", entry.after.items()))
    elif entry.action == "delete":
        sections.extend(_format_section("Було", entry.before.items()))
    else:
        sections.extend(_format_section("Було", entry.before.items()))
        sections.extend(_format_section("Стало", entry.after.items()))
    return "\n".join(sections)


def _format_section(title: str, items: Iterable[tuple[str, Any]]) -> list[str]:
    items = list(items)
    if not items:
        return []
    lines = [f"<b>{title}:</b>"]
    for key, value in sorted(items):
        lines.append(
            f"• <code>{escape(str(key))}</code>: {escape(_format_value(value))}"
        )
    return lines


def _format_value(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value}"
    if isinstance(value, bool):
        return "так" if value else "ні"
    if value is None:
        return "—"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


__all__ = ["router"]
