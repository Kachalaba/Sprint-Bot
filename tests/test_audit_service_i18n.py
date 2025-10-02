from __future__ import annotations

import asyncio
import json
from datetime import datetime
from html import escape
from types import SimpleNamespace
from typing import Any

import pytest

from handlers import admin_history
from i18n import reset_context_language, set_context_language, t
from services.audit_service import AuditEntry


class _DummyMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)


class _DummyCallback:
    def __init__(self) -> None:
        self.answers: list[tuple[str, bool]] = []
        self.message = _DummyMessage()

    async def answer(self, text: str, show_alert: bool = False) -> None:
        self.answers.append((text, show_alert))


class _StubAuditService:
    def __init__(self, *, undo_result: bool) -> None:
        self.undo_result = undo_result
        self.called_with: list[int] = []

    async def undo(self, op_id: int) -> bool:
        self.called_with.append(op_id)
        return self.undo_result


def _expected_value(value: Any) -> str:
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


def _build_section(section: str, data: dict[str, Any]) -> str:
    if not data:
        return ""
    title_key = (
        "audit.section.before_title"
        if section == "before"
        else "audit.section.after_title"
    )
    lines = ["", t(title_key)]
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
def test_audit_history_entry_translated(lang: str) -> None:
    entry = AuditEntry(
        id=11,
        user_id=77,
        action="update",
        entity_type="result",
        entity_id="42",
        before={"is_pr": False, "time": "61.00", "comment": None},
        after={"is_pr": True, "time": "60.20", "comment": "Nice"},
        ts=datetime(2024, 3, 4, 15, 6, 7),
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
    finally:
        reset_context_language(token)


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_audit_handle_undo_translated(lang: str) -> None:
    async def scenario() -> None:
        token = set_context_language(lang)
        try:
            callback_data = SimpleNamespace(op_id=5)

            success_callback = _DummyCallback()
            success_service = _StubAuditService(undo_result=True)
            await admin_history.handle_undo(
                success_callback,
                callback_data,
                success_service,
            )
            assert success_service.called_with == [callback_data.op_id]
            assert success_callback.answers == [(t("audit.undo_ok"), False)]
            assert success_callback.message.answers == [
                t("audit.undo_done", op_id=callback_data.op_id)
            ]

            failure_callback = _DummyCallback()
            failure_service = _StubAuditService(undo_result=False)
            await admin_history.handle_undo(
                failure_callback,
                callback_data,
                failure_service,
            )
            assert failure_service.called_with == [callback_data.op_id]
            assert failure_callback.answers == [(t("audit.undo_fail"), True)]
            assert failure_callback.message.answers == []
        finally:
            reset_context_language(token)

    asyncio.run(scenario())
