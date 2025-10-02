"""Handlers for CSV import/export commands."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Mapping

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

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
        await message.answer("Використання: /export <user|team|all>.")
        return

    athlete_ids: tuple[int, ...] | None
    if scope == "user":
        athlete_ids = (user_id,)
    elif scope == "team":
        role = await role_service.get_role(user_id)
        if role not in {ROLE_TRAINER, ROLE_ADMIN}:
            await message.answer("Експорт команди доступний лише тренерам.")
            return
        accessible = await role_service.get_accessible_athletes(user_id)
        athlete_ids = tuple(sorted(set(int(value) for value in accessible)))
        if not athlete_ids:
            await message.answer("Немає спортсменів для експорту.")
            return
    else:  # scope == "all"
        role = await role_service.get_role(user_id)
        if role != ROLE_ADMIN:
            await message.answer("Експорт всіх результатів доступний лише адміністраторам.")
            return
        athlete_ids = None

    data = await io_service.export_results(athlete_ids=athlete_ids)
    if not data:
        await message.answer("Немає результатів для експорту.")
        return

    file_name = _build_file_name(scope)
    document = BufferedInputFile(data, filename=file_name)
    await message.answer_document(
        document,
        caption=f"Всього записів: {_count_rows(data)}",
    )


@router.message(Command("import_csv"), require_roles(ROLE_TRAINER, ROLE_ADMIN))
async def start_import(message: types.Message, state: FSMContext) -> None:
    """Prompt user to upload CSV file for import."""

    await state.clear()
    await state.set_state(ImportStates.waiting_file)
    await message.answer(
        "Надішліть CSV-файл у форматі UTF-8. Спочатку виконується перевірка (dry-run)."
    )


@router.message(ImportStates.waiting_file, F.document)
async def handle_import_file(
    message: types.Message,
    state: FSMContext,
    io_service: IOService,
) -> None:
    """Receive CSV file, run dry-run validation and show summary."""

    document = message.document
    if document is None:
        await message.answer("Очікується файл формату CSV.")
        return
    if document.file_name and not document.file_name.lower().endswith(".csv"):
        await message.answer("Потрібен файл з розширенням .csv.")
        return
    if document.file_size and document.file_size > 5 * 1024 * 1024:
        await message.answer("Файл завеликий. Обмеження — 5 МБ.")
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
        await callback.message.edit_text("Сесія імпорту не знайдена. Повторіть команду /import_csv.")
        await state.clear()
        return
    if not preview.rows:
        await callback.message.edit_text(
            "Немає валідних рядків для імпорту. Надішліть новий файл /import_csv.",
            reply_markup=None,
        )
        await state.clear()
        return

    actor_id = callback.from_user.id if callback.from_user else None
    result = await io_service.apply_import(preview, user_id=actor_id)
    await state.clear()
    await callback.message.edit_text(
        _format_result(preview, result), reply_markup=None
    )


@router.callback_query(ImportStates.confirm, F.data == CANCEL_CALLBACK)
async def cancel_import(callback: CallbackQuery, state: FSMContext) -> None:
    """Abort import process and clear state."""

    await callback.answer("Імпорт скасовано")
    await state.clear()
    await callback.message.edit_text("Імпорт скасовано.", reply_markup=None)


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
    lines = [
        "Результат перевірки CSV:",
        f"• Рядків у файлі: {preview.total_rows}",
        f"• Готово до імпорту: {len(preview.rows)}",
        f"• З помилками/дублікатами: {len(preview.issues)}",
    ]
    if preview.issues:
        lines.append("\nПроблеми:")
        for issue in preview.issues[:10]:
            lines.append(f"  · рядок {issue.row_number}: {issue.message}")
        if len(preview.issues) > 10:
            lines.append(f"… та ще {len(preview.issues) - 10} рядків")
    return "\n".join(lines)


def _build_preview_keyboard(preview: ImportPreview) -> InlineKeyboardMarkup | None:
    if preview.rows:
        buttons = [
            [InlineKeyboardButton(text="✅ Підтвердити", callback_data=CONFIRM_CALLBACK)],
            [InlineKeyboardButton(text="✖️ Скасувати", callback_data=CANCEL_CALLBACK)],
        ]
    else:
        buttons = [[InlineKeyboardButton(text="✖️ Закрити", callback_data=CANCEL_CALLBACK)]]
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
    return (
        "Імпорт завершено.\n"
        f"• Оброблено рядків: {preview.total_rows}\n"
        f"• Додано записів: {inserted}\n"
        f"• Пропущено (дублікатів): {skipped + duplicate_issues}\n"
        + (f"• Залишилось з помилками: {error_rows}" if error_rows else "")
    )


def _count_rows(data: bytes) -> int:
    text = data.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    return max(len(lines) - 1, 0)


__all__ = ["router"]
