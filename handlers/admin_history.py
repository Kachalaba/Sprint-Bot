from __future__ import annotations

import json
from datetime import datetime
from html import escape
from typing import Any, Iterable

from aiogram import Router, types
from aiogram.filters import Command

from i18n import t
from keyboards import AuditUndoCB, build_audit_entry_keyboard
from role_service import ROLE_ADMIN, ROLE_TRAINER
from services.audit_service import AuditEntry, AuditService
from utils.roles import require_roles

router = Router()

_ACTION_LABEL_KEYS: dict[str, str] = {
    "create": "audit.action.create",
    "update": "audit.action.update",
    "delete": "audit.action.delete",
}

_ENTITY_LABEL_KEYS: dict[str, str] = {
    "result": "audit.entity.result",
    "template": "audit.entity.template",
}

_SECTION_TITLE_KEYS: dict[str, str] = {
    "before": "audit.section.before_title",
    "after": "audit.section.after_title",
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
        await message.answer(t("audit.empty"))
        return

    await message.answer(t("audit.title"))

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
        await callback.answer(t("audit.undo_fail"), show_alert=True)
        return
    await callback.answer(t("audit.undo_ok"))
    if callback.message:
        await callback.message.answer(
            t("audit.undo_done", op_id=callback_data.op_id)
        )


def _parse_arguments(text: str) -> tuple[int, int | None, str | None]:
    parts = text.strip().split()
    if len(parts) < 2:
        return _DEFAULT_LIMIT, None, None
    keyword = parts[1].lower()
    if keyword == "last":
        if len(parts) < 3:
            return _DEFAULT_LIMIT, None, t("audit.args.missing_limit")
        try:
            limit = max(1, min(20, int(parts[2])))
        except ValueError:
            return _DEFAULT_LIMIT, None, t("audit.args.invalid_limit")
        return limit, None, None
    if keyword == "user":
        if len(parts) < 3:
            return _DEFAULT_LIMIT, None, t("audit.args.missing_user")
        try:
            user_id = int(parts[2])
        except ValueError:
            return _DEFAULT_LIMIT, None, t("audit.args.invalid_user")
        return _DEFAULT_LIMIT, user_id, None
    return _DEFAULT_LIMIT, None, t("audit.args.unknown")


def _format_entry(entry: AuditEntry) -> str:
    timestamp = entry.ts.strftime("%Y-%m-%d %H:%M:%S")
    entity_label = _translate_entity(entry.entity_type)
    action_label = _translate_action(entry.action)
    what = t(
        "audit.what",
        entity=entity_label,
        entity_id=escape(entry.entity_id),
        action=action_label,
    )
    before_text = ""
    after_text = ""
    if entry.action == "create":
        after_text = _format_section_text("after", (entry.after or {}).items())
    elif entry.action == "delete":
        before_text = _format_section_text("before", (entry.before or {}).items())
    else:
        before_text = _format_section_text("before", (entry.before or {}).items())
        after_text = _format_section_text("after", (entry.after or {}).items())
    return t(
        "audit.item",
        id=entry.id,
        when=timestamp,
        who=escape(str(entry.user_id)),
        what=what,
        before=before_text,
        after=after_text,
    )


def _format_section_text(
    section: str, items: Iterable[tuple[str, Any]]
) -> str:
    pairs = sorted(items)
    if not pairs:
        return ""
    title_key = _SECTION_TITLE_KEYS.get(section)
    title = t(title_key) if title_key else section.title()
    lines = ["", title]
    for key, value in pairs:
        lines.append(
            t(
                "audit.section.item",
                field=escape(str(key)),
                value=escape(_format_value(value)),
            )
        )
    return "\n".join(lines)


def _format_value(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value}"
    if isinstance(value, bool):
        return t("audit.value.true") if value else t("audit.value.false")
    if value is None:
        return t("audit.value.none")
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _translate_action(action: str) -> str:
    key = _ACTION_LABEL_KEYS.get(action)
    return t(key) if key else action


def _translate_entity(entity: str) -> str:
    key = _ENTITY_LABEL_KEYS.get(entity)
    return t(key) if key else entity.title()


__all__ = ["router"]
