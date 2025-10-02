"""Handlers for CSV import/export commands."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Mapping

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from i18n import t
from role_service import ROLE_ADMIN, ROLE_TRAINER, RoleService
from services.io_service import ImportIssue, ImportPreview, ImportRecord, IOService
from utils.roles import require_roles

router = Router()


class ImportStates(StatesGroup):
    """FSM states for CSV import workflow."""

    waiting_file = State()
    confirm = State()


CONFIRM_CALLBACK = "io:confirm"
CANCEL_CALLBACK = "io:cancel"


@router.message(Command("export"))
async def export_results(
    message: types.Message,
    io_service: IOService,
    role_service: RoleService,
) -> None:
    """Handle /export command and send CSV file back to requester."""

    if not message.from_user:
        return
    user_id = message.from_user.id
    scope = _extract_scope(message.text or "")
    if scope is None:
        await message.answer(t("expimp.export.usage"))
        return

    athlete_ids: tuple[int, ...] | None
    if scope == "user":
        athlete_ids = (user_id,)
    elif scope == "team":
        role = await role_service.get_role(user_id)
        if role not in {ROLE_TRAINER, ROLE_ADMIN}:
            await message.answer(t("expimp.export.team_forbidden"))
            return
        accessible = await role_service.get_accessible_athletes(user_id)
        athlete_ids = tuple(sorted(set(int(value) for value in accessible)))
        if not athlete_ids:
            await message.answer(t("expimp.export.team_empty"))
            return
    else:  # scope == "all"
        role = await role_service.get_role(user_id)
        if role != ROLE_ADMIN:
            await message.answer(t("expimp.export.all_forbidden"))
            return
        athlete_ids = None

    data = await io_service.export_results(athlete_ids=athlete_ids)
    if not data:
        await message.answer(t("expimp.export.no_results"))
        return

    file_name = _build_file_name(scope)
    document = BufferedInputFile(data, filename=file_name)
    await message.answer(t("expimp.export.sending"))
    await message.answer_document(
        document,
        caption=t("expimp.export.summary", count=_count_rows(data)),
    )


@router.message(Command("import_csv"), require_roles(ROLE_TRAINER, ROLE_ADMIN))
async def start_import(message: types.Message, state: FSMContext) -> None:
    """Prompt user to upload CSV file for import."""

    await state.clear()
    await state.set_state(ImportStates.waiting_file)
    await message.answer(t("expimp.import.prompt"))


@router.message(ImportStates.waiting_file, F.document)
async def handle_import_file(
    message: types.Message,
    state: FSMContext,
    io_service: IOService,
) -> None:
    """Receive CSV file, run dry-run validation and show summary."""

    document = message.document
    if document is None:
        await message.answer(t("expimp.import.expect_file"))
        return
    if document.file_name and not document.file_name.lower().endswith(".csv"):
        await message.answer(t("expimp.import.invalid_ext"))
        return
    if document.file_size and document.file_size > 5 * 1024 * 1024:
        await message.answer(t("expimp.import.too_large"))
        return
    buffer = io.BytesIO()
    await message.bot.download(document, destination=buffer)
    preview = await io_service.dry_run_import(buffer.getvalue())

    await state.update_data(preview=_serialize_preview(preview))
    await state.set_state(ImportStates.confirm)
    await message.answer(
        _format_preview(preview),
        reply_markup=_build_preview_keyboard(preview),
    )


@router.callback_query(ImportStates.confirm, F.data == CONFIRM_CALLBACK)
async def confirm_import(
    callback: CallbackQuery,
    state: FSMContext,
    io_service: IOService,
) -> None:
    """Persist validated rows after confirmation."""

    await callback.answer()
    data = await state.get_data()
    preview = _deserialize_preview(data.get("preview"))
    if preview is None:
        await callback.message.edit_text(
            t("expimp.import.session_missing", command="/import_csv"),
        )
        await state.clear()
        return
    if not preview.rows:
        await callback.message.edit_text(
            t("expimp.import.no_valid_rows", command="/import_csv"),
            reply_markup=None,
        )
        await state.clear()
        return

    actor_id = callback.from_user.id if callback.from_user else None
    result = await io_service.apply_import(preview, user_id=actor_id)
    await state.clear()
    await callback.message.edit_text(_format_result(preview, result), reply_markup=None)


@router.callback_query(ImportStates.confirm, F.data == CANCEL_CALLBACK)
async def cancel_import(callback: CallbackQuery, state: FSMContext) -> None:
    """Abort import process and clear state."""

    await callback.answer(t("expimp.import.cancelled_toast"))
    await state.clear()
    await callback.message.edit_text(t("expimp.import.cancelled"), reply_markup=None)


def _extract_scope(text: str) -> str | None:
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    scope = parts[1].strip().lower()
    if scope not in {"user", "team", "all"}:
        return None
    return scope


def _build_file_name(scope: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"results_{scope}_{timestamp}.csv"


def _format_preview(preview: ImportPreview) -> str:
    issue_count = len(preview.issues)
    lines = [
        t("expimp.dry_run.title"),
        (
            t(
                "expimp.dry_run.status.errors",
                count=issue_count,
            )
            if issue_count
            else t("expimp.dry_run.status.ok")
        ),
        t("expimp.dry_run.total", count=preview.total_rows),
        t("expimp.dry_run.ready", count=len(preview.rows)),
        t("expimp.dry_run.invalid", count=issue_count),
    ]
    if issue_count:
        lines.append("")
        lines.append(t("expimp.dry_run.issues_title"))
        for issue in preview.issues[:10]:
            lines.append(
                t(
                    "expimp.dry_run.issue_line",
                    row=issue.row_number,
                    reason=issue.message,
                )
            )
        if issue_count > 10:
            lines.append(
                t(
                    "expimp.dry_run.issue_more",
                    count=issue_count - 10,
                )
            )
    lines.append("")
    lines.append(t("expimp.import.confirm_question"))
    return "\n".join(lines).strip()


def _build_preview_keyboard(preview: ImportPreview) -> InlineKeyboardMarkup | None:
    if preview.rows:
        buttons = [
            [
                InlineKeyboardButton(
                    text=t("expimp.buttons.confirm"), callback_data=CONFIRM_CALLBACK
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("expimp.buttons.cancel"), callback_data=CANCEL_CALLBACK
                )
            ],
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton(
                    text=t("expimp.buttons.close"), callback_data=CANCEL_CALLBACK
                )
            ]
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _serialize_preview(preview: ImportPreview) -> dict[str, Any]:
    return {
        "rows": [
            {
                "row_number": row.row_number,
                "athlete_id": row.athlete_id,
                "athlete_name": row.athlete_name,
                "stroke": row.stroke,
                "distance": row.distance,
                "total_seconds": row.total_seconds,
                "timestamp": row.timestamp.isoformat(),
                "is_pr": row.is_pr,
            }
            for row in preview.rows
        ],
        "issues": [
            {"row_number": issue.row_number, "message": issue.message}
            for issue in preview.issues
        ],
        "total_rows": preview.total_rows,
    }


def _deserialize_preview(data: Mapping[str, Any] | None) -> ImportPreview | None:
    if not data:
        return None
    try:
        rows = tuple(
            ImportRecord(
                row_number=int(item["row_number"]),
                athlete_id=int(item["athlete_id"]),
                athlete_name=str(item["athlete_name"]),
                stroke=str(item["stroke"]),
                distance=int(item["distance"]),
                total_seconds=float(item["total_seconds"]),
                timestamp=datetime.fromisoformat(str(item["timestamp"])),
                is_pr=bool(item["is_pr"]),
            )
            for item in data.get("rows", [])
        )
        issues = tuple(
            ImportIssue(
                row_number=int(item["row_number"]),
                message=str(item["message"]),
            )
            for item in data.get("issues", [])
        )
        total_rows = int(data.get("total_rows", 0))
    except (ValueError, KeyError, TypeError):
        return None
    return ImportPreview(rows=rows, issues=issues, total_rows=total_rows)


def _format_result(preview: ImportPreview, result: Any) -> str:
    inserted = getattr(result, "inserted", 0)
    skipped = getattr(result, "skipped", 0)
    duplicate_issues = sum(
        1 for issue in preview.issues if "duplicate" in issue.message
    )
    error_rows = max(len(preview.issues) - duplicate_issues, 0)
    lines = [
        t("expimp.result.title"),
        t("expimp.result.processed", count=preview.total_rows),
        t("expimp.result.inserted", count=inserted),
        t("expimp.result.skipped", count=skipped + duplicate_issues),
    ]
    if error_rows:
        lines.append(t("expimp.result.errors", count=error_rows))
    return "\n".join(lines)


def _count_rows(data: bytes) -> int:
    text = data.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    return max(len(lines) - 1, 0)


__all__ = ["router"]
