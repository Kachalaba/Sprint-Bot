from __future__ import annotations

import json
from datetime import datetime
from html import escape

import pytest

from handlers import admin_history
from i18n import reset_context_language, set_context_language, t
from keyboards import build_audit_entry_keyboard
from services.audit_service import AuditEntry

_SECTION_KEYS = {
    "before": "audit.section.before_title",
    "after": "audit.section.after_title",
}


def _expected_value(value: object) -> str:
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


def _build_section(section: str, data: dict[str, object]) -> str:
    if not data:
        return ""
    lines = ["", t(_SECTION_KEYS[section])]
    for key, value in sorted(data.items()):
        lines.append(
            t(
                "audit.section.item",
                field=escape(str(key)),
                value=escape(_expected_value(value)),
            )
        )
    return "\n".join(lines)


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_admin_history_entry_and_button_translations(lang: str) -> None:
    entry = AuditEntry(
        id=7,
        user_id=101,
        action="update",
        entity_type="result",
        entity_id="55",
        before={"is_pr": False, "time": "60.00", "comment": None},
        after={"is_pr": True, "time": "59.50", "comment": "Great"},
        ts=datetime(2024, 1, 2, 13, 45, 0),
    )

    token = set_context_language(lang)
    try:
        text = admin_history._format_entry(entry)
        expected_what = t(
            "audit.what",
            entity=t("audit.entity.result"),
            entity_id=escape(entry.entity_id),
            action=t("audit.action.update"),
        )
        expected_text = t(
            "audit.item",
            id=entry.id,
            when=entry.ts.strftime("%Y-%m-%d %H:%M:%S"),
            who=escape(str(entry.user_id)),
            what=expected_what,
            before=_build_section("before", entry.before),
            after=_build_section("after", entry.after),
        )
        assert text == expected_text

        keyboard = build_audit_entry_keyboard(entry.id)
        button_texts = [
            button.text for row in keyboard.inline_keyboard for button in row
        ]
        assert button_texts == [t("audit.btn.undo")]
    finally:
        reset_context_language(token)
