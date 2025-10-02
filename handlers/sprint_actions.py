"""Sprint-related handlers and UI helpers.

Приклад взаємодії користувача:

1. Натискає «Додати результат ➕» → бот показує кнопки дистанцій.
2. Обирає «🔥 100 м кроль» із шаблонів → бот одразу просить час першого відрізку.
3. Вводить проміжні результати у форматі ``0:32.45`` → бот підказує наступні відрізки.
4. Отримує підсумок з аналізом та кнопку «🔁 Повторити попередній результат».
5. Натискає «🔁» → бот дублює результат з новим часом та аналізом.
"""

from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from i18n import t

from .add_result import build_quick_prompt, build_quick_saved
from keyboards import (
    CommentCB,
    DistanceCB,
    RepeatCB,
    StrokeCB,
    TemplateCB,
    get_comment_prompt_keyboard,
    get_distance_keyboard,
    get_result_actions_keyboard,
    get_stroke_keyboard,
    get_template_keyboard,
    pack_timestamp_for_callback,
    unpack_timestamp_from_callback,
)
from notifications import NotificationService
from role_service import ROLE_ATHLETE, ROLE_TRAINER, RoleService
from services import ws_athletes, ws_log, ws_pr, ws_results
from template_service import TemplateService
from services.stats_service import SobStats, calc_segment_prs, calc_sob, calc_total_pr
from utils import AddResult, fmt_time, get_segments, pr_key, speed
from utils.parse_time import parse_splits, parse_total, validate_splits

router = Router()


# (coach_id, athlete_id) -> stored data for quick repeat
LAST_RESULTS: dict[tuple[int, int], dict[str, Any]] = {}

COMMENT_COLUMN_INDEX = 8


def _normalize_comment(comment: str | None) -> str:
    """Return trimmed comment or empty string."""

    if not comment:
        return ""
    return comment.strip()


def _comment_to_html(comment: str) -> str:
    """Escape comment text for safe HTML rendering."""

    return html.escape(comment, quote=True)


def _find_result_row(athlete_id: int, timestamp: str) -> int:
    """Return worksheet row index for result with provided timestamp."""

    rows = ws_results.get_all_values()
    for idx, row in enumerate(rows, start=1):
        if len(row) < 5:
            continue
        if str(row[0]) != str(athlete_id):
            continue
        if row[4] == timestamp:
            return idx
    raise ValueError("Result row not found")


def _update_comment(athlete_id: int, timestamp: str, comment: str | None) -> None:
    """Persist comment for the given result."""

    normalized = _normalize_comment(comment)
    row_idx = _find_result_row(athlete_id, timestamp)
    ws_results.update_cell(row_idx, COMMENT_COLUMN_INDEX, normalized)


def _sync_last_results(timestamp: str, comment: str) -> None:
    """Update cached last results with a new comment value."""

    for payload in LAST_RESULTS.values():
        if payload.get("timestamp") == timestamp:
            payload["comment"] = comment


def _build_comment_edit_keyboard(
    timestamp: str, athlete_id: int
) -> InlineKeyboardMarkup:
    """Return keyboard with comment edit actions."""

    packed = pack_timestamp_for_callback(timestamp)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Видалити нотатку",
                    callback_data=CommentCB(
                        action="clear", ts=packed, athlete_id=athlete_id
                    ).pack(),
                )
            ],
            [InlineKeyboardButton(text="⬅️ Скасувати", callback_data="comment_cancel")],
        ]
    )


def _segment_prompt(idx: int, length: float) -> str:
    """Return formatted prompt for segment input."""

    return build_quick_prompt(idx, length)


def _load_best_total(athlete_id: int, stroke: str, dist: int) -> float | None:
    """Return previous best total time for athlete if available."""

    try:
        rows = ws_results.get_all_values()
    except Exception as exc:  # pragma: no cover - network dependent
        logging.warning("Failed to load previous totals: %s", exc, exc_info=True)
        return None

    best: float | None = None
    for row in rows:
        if not row or len(row) < 7:
            continue
        try:
            uid = int(row[0])
            row_stroke = str(row[2])
            row_dist = int(row[3])
            total_raw = row[6]
        except (ValueError, IndexError, TypeError):
            continue
        if uid != athlete_id or row_stroke != stroke or row_dist != dist:
            continue
        try:
            total_value = float(str(total_raw).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if best is None or total_value < best:
            best = total_value
    return best


def _load_segment_bests(
    athlete_id: int, stroke: str, dist: int
) -> tuple[list[float | None], dict[int, int]]:
    """Return stored best segment times and their worksheet rows."""

    try:
        rows = ws_pr.get_all_values()
    except Exception as exc:  # pragma: no cover - network dependent
        logging.warning("Failed to load segment PRs: %s", exc, exc_info=True)
        return [], {}

    values: dict[int, float] = {}
    rows_map: dict[int, int] = {}
    for row_idx, row in enumerate(rows, start=1):
        if not row or len(row) < 2:
            continue
        key = row[0]
        try:
            uid_str, stroke_key, dist_str, seg_idx_str = key.split("|")
            uid = int(uid_str)
            seg_idx = int(seg_idx_str)
            dist_val = int(dist_str)
        except (ValueError, AttributeError):
            continue
        if uid != athlete_id or stroke_key != stroke or dist_val != dist:
            continue
        try:
            value = float(str(row[1]).replace(",", "."))
        except (TypeError, ValueError):
            continue
        values[seg_idx] = value
        rows_map[seg_idx] = row_idx

    if not values:
        return [], rows_map

    max_idx = max(values)
    best_list: list[float | None] = [None] * (max_idx + 1)
    for idx, value in values.items():
        best_list[idx] = value
    return best_list, rows_map


def _persist_result(
    athlete_id: int,
    athlete_name: str,
    stroke: str,
    dist: int,
    splits: Iterable[float],
    comment: str | None = None,
) -> tuple[float, list[tuple[int, float]], str, dict[str, Any]]:
    """Save result to Google Sheets and return totals with PR info."""

    splits_list = list(splits)
    total = sum(splits_list)
    validate_splits(total, splits_list)
    timestamp = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")

    previous_total = _load_best_total(athlete_id, stroke, dist)
    segment_bests, segment_rows = _load_segment_bests(athlete_id, stroke, dist)
    total_stats = calc_total_pr(previous_total, total)
    segment_flags = calc_segment_prs(segment_bests, splits_list)
    sob_stats: SobStats = calc_sob(segment_bests, splits_list)

    stats_payload: dict[str, Any] = {
        "new_total_pr": total_stats.is_new,
        "total_pr_delta": total_stats.delta,
        "previous_total": total_stats.previous,
        "segment_prs": segment_flags,
        "sob_delta": sob_stats.delta,
        "sob_previous": sob_stats.previous,
        "sob_current": sob_stats.current,
    }

    ws_results.append_row(
        [
            athlete_id,
            athlete_name,
            stroke,
            dist,
            timestamp,
            json.dumps(splits_list),
            total,
            _normalize_comment(comment),
        ]
    )
    ws_log.append_row([athlete_id, timestamp, "ADD", json.dumps(splits_list)])

    new_prs: list[tuple[int, float]] = []
    best_buffer = list(segment_bests)
    if len(best_buffer) < len(splits_list):
        best_buffer.extend([None] * (len(splits_list) - len(best_buffer)))

    for idx, seg_time in enumerate(splits_list):
        key = pr_key(athlete_id, stroke, dist, idx)
        row_idx = segment_rows.get(idx)
        current_best = best_buffer[idx] if idx < len(best_buffer) else None
        if row_idx is None:
            ws_pr.append_row([key, seg_time, timestamp])
            new_prs.append((idx, seg_time))
            continue
        if current_best is not None and seg_time >= current_best:
            continue
        ws_pr.update(f"A{row_idx}:C{row_idx}", [[key, seg_time, timestamp]])
        new_prs.append((idx, seg_time))

    return total, new_prs, timestamp, stats_payload


def _analysis_text(
    dist: int,
    splits: list[float],
    total: float,
    segments: Iterable[float] | None = None,
) -> str:
    """Compose analysis block for the result."""

    seg_lens = [float(seg) for seg in (segments or get_segments(dist))]
    speeds = [speed(seg, t) for seg, t in zip(seg_lens, splits)]
    avg_speed = speed(dist, total)
    pace = total / dist * 100 if dist else 0
    degradation = (
        (speeds[0] - speeds[-1]) / speeds[0] * 100
        if len(speeds) > 1 and speeds[0]
        else 0
    )

    segments_line = " • ".join(f"{v:.2f} м/с" for v in speeds)

    return (
        "📊 <b>Аналіз результату</b>\n"
        f"• Швидкості по сегментах: {segments_line}\n"
        f"• Середня швидкість: {avg_speed:.2f} м/с\n"
        f"• Темп: {pace:.1f} сек/100 м\n"
        f"• Деградація темпу: {degradation:.1f}%"
    )


def _format_result_summary(
    dist: int,
    total: float,
    new_prs: Sequence[tuple[int, float]],
    stats: dict[str, Any],
    comment: str | None,
) -> str:
    """Compose short HTML summary for saved result."""

    summary = build_quick_saved(dist, total)
    if stats.get("new_total_pr"):
        delta = stats.get("total_pr_delta") or 0.0
        delta_suffix = f" (−{delta:.2f} с)" if delta else ""
        summary += f"\n🏆 Новий загальний PR{delta_suffix}!"
    if new_prs:
        summary += "\n" + "\n".join(
            f"🥳 Новий PR сегменту #{idx + 1}: {fmt_time(value)}"
            for idx, value in new_prs
        )
    sob_delta = float(stats.get("sob_delta") or 0.0)
    if sob_delta > 0:
        sob_current = stats.get("sob_current")
        current_label = (
            f" → {fmt_time(float(sob_current))}"
            if sob_current is not None
            else ""
        )
        summary += f"\nΣ SoB покращено на {sob_delta:.2f} с{current_label}"
    if comment:
        summary += f"\n📝 Нотатка: {_comment_to_html(comment)}"
    return summary


async def _finalize_result_entry(
    target: types.Message,
    actor: types.User,
    state: FSMContext,
    comment: str | None,
    notifications: NotificationService,
    role_service: RoleService,
) -> None:
    """Persist result and share summary with optional comment."""

    data = await state.get_data()
    try:
        splits = parse_splits(data.get("splits") or [])
    except ValueError as exc:
        logging.warning("Invalid splits in state: %s", exc)
        await state.clear()
        await target.answer(
            "Не вдалося розпізнати часи відрізків. Почніть заново, будь ласка."
        )
        return

    if not splits:
        await state.clear()
        await target.answer("Немає даних для збереження. Почніть заново.")
        return

    athlete_id = data.get("athlete_id", actor.id)
    stroke = data.get("stroke", "freestyle")
    dist = data["dist"]
    segments: Iterable[float] | None = data.get("segments")
    comment_clean = _normalize_comment(comment)

    await state.clear()

    try:
        total, new_prs, timestamp, stats_payload = _persist_result(
            athlete_id,
            actor.full_name,
            stroke,
            dist,
            splits,
            comment=comment_clean,
        )
    except Exception as exc:
        logging.error("Failed to save result to Google Sheets: %s", exc, exc_info=True)
        await target.answer("Помилка при збереженні результату. Спробуйте пізніше.")
        return

    summary = _format_result_summary(dist, total, new_prs, stats_payload, comment_clean)

    keyboard = get_result_actions_keyboard(
        athlete_id=athlete_id,
        timestamp=timestamp,
        has_comment=bool(comment_clean),
    )

    await target.answer(summary, parse_mode="HTML", reply_markup=keyboard)

    analysis_text = _analysis_text(dist, splits, total, segments)
    await target.answer(analysis_text, parse_mode="HTML")

    trainers = await role_service.trainers_for_athlete(athlete_id)
    await notifications.notify_new_result(
        actor_id=actor.id,
        actor_name=actor.full_name,
        athlete_id=athlete_id,
        athlete_name=actor.full_name,
        dist=dist,
        stroke=stroke,
        total=total,
        timestamp=timestamp,
        stats=stats_payload,
        trainers=trainers,
        new_prs=new_prs,
    )

    LAST_RESULTS[(actor.id, athlete_id)] = {
        "athlete_id": athlete_id,
        "athlete_name": actor.full_name,
        "stroke": stroke,
        "dist": dist,
        "splits": list(splits),
        "segments": list(float(seg) for seg in (segments or get_segments(dist))),
        "timestamp": timestamp,
        "comment": comment_clean,
    }


@router.callback_query(F.data == "add")
async def add(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Start collecting sprint result."""

    await cb.message.answer(
        "Оберіть дистанцію або введіть вручну:",
        reply_markup=get_distance_keyboard(),
    )
    await state.set_state(AddResult.choose_dist)
    await cb.answer()


@router.callback_query(DistanceCB.filter(), AddResult.choose_dist)
async def distance_selected(
    cb: types.CallbackQuery, callback_data: DistanceCB, state: FSMContext
) -> None:
    """Handle distance choice from keyboard."""

    await cb.answer()
    dist = callback_data.value
    segments = get_segments(dist)
    await state.update_data(dist=dist, splits=[], idx=0, segments=segments)
    await cb.message.answer(
        f"Дистанція {dist} м. Оберіть стиль:", reply_markup=get_stroke_keyboard()
    )
    await state.set_state(AddResult.waiting_for_stroke)


@router.callback_query(F.data == "manual_distance", AddResult.choose_dist)
async def manual_distance(cb: types.CallbackQuery) -> None:
    """Prompt manual distance entry."""

    await cb.answer()
    await cb.message.answer(
        "Введіть дистанцію цифрами у метрах. Наприклад: 75, 125 або 300.",
    )


@router.callback_query(F.data == "choose_template", AddResult.choose_dist)
async def choose_template(
    cb: types.CallbackQuery, template_service: TemplateService
) -> None:
    """Show list of sprint templates."""

    await cb.answer()
    templates = await template_service.list_templates()
    if not templates:
        await cb.message.answer(
            "Немає збережених шаблонів. Створіть їх командою /templates.",
        )
        return
    template_pairs = ((tpl.template_id, tpl.title) for tpl in templates)
    await cb.message.answer(
        "📋 Шаблони спринтів. Оберіть потрібний:",
        reply_markup=get_template_keyboard(template_pairs),
    )


@router.callback_query(F.data == "back_to_distance")
async def back_to_distance(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Return to distance selection keyboard."""

    await cb.answer()
    await cb.message.answer(
        "Повертаємося до вибору дистанції:",
        reply_markup=get_distance_keyboard(),
    )
    await state.set_state(AddResult.choose_dist)


@router.callback_query(TemplateCB.filter(), AddResult.choose_dist)
async def template_selected(
    cb: types.CallbackQuery,
    callback_data: TemplateCB,
    state: FSMContext,
    template_service: TemplateService,
) -> None:
    """Handle template selection and jump straight to time collection."""

    template = await template_service.get_template(callback_data.template_id)
    if not template:
        await cb.answer("Шаблон не знайдено", show_alert=True)
        return

    await cb.answer()
    segs = list(template.segments_or_default())
    await state.update_data(
        dist=template.dist,
        splits=[],
        idx=0,
        stroke=template.stroke,
        template_id=template.template_id,
        segments=[float(seg) for seg in segs],
    )
    await state.set_state(AddResult.collect)
    hint = f"💡 {template.hint}" if template.hint else ""
    segments_line = " + ".join(f"{seg:g} м" for seg in segs)
    await cb.message.answer(
        "✅ Обрано шаблон «{title}».\n{hint}\nРозбивка: {segments}\n{prompt}".format(
            title=template.title,
            hint=hint,
            segments=segments_line,
            prompt=_segment_prompt(0, segs[0]),
        )
    )


@router.message(AddResult.choose_dist)
async def dist_chosen(message: types.Message, state: FSMContext) -> None:
    """Handle chosen distance."""

    try:
        dist = int(message.text)
    except ValueError:
        return await message.reply("❗ Дистанція має бути числом у метрах. Приклад: 75")
    if dist <= 0:
        return await message.reply("❗ Дистанція має бути більшою за нуль.")
    segments = get_segments(dist)
    await state.update_data(dist=dist, splits=[], idx=0, segments=segments)
    await message.answer(
        f"Дистанція {dist} м. Оберіть стиль:", reply_markup=get_stroke_keyboard()
    )
    await state.set_state(AddResult.waiting_for_stroke)


@router.callback_query(StrokeCB.filter())
async def stroke_chosen(
    cb: types.CallbackQuery, callback_data: StrokeCB, state: FSMContext
) -> None:
    """Save stroke and ask for first split."""

    await cb.answer()
    await state.update_data(stroke=callback_data.stroke)
    data = await state.get_data()
    dist = data["dist"]
    segments = data.get("segments") or get_segments(dist)
    segments_list = list(float(seg) for seg in segments)
    await state.update_data(segments=segments_list)
    await cb.message.answer(_segment_prompt(0, segments_list[0]))
    await state.set_state(AddResult.collect)


@router.message(AddResult.collect)
async def collect(message: types.Message, state: FSMContext) -> None:
    """Collect segment times and save result."""

    data = await state.get_data()
    athlete_id = data.get("athlete_id", message.from_user.id)
    dist, idx, splits = data["dist"], data["idx"], data["splits"]
    raw_segments = data.get("segments") or get_segments(dist)
    segments = [float(seg) for seg in raw_segments]
    if data.get("segments") != segments:
        await state.update_data(segments=segments)
    raw_value = message.text or ""
    try:
        t = parse_total(raw_value)
    except ValueError:
        return await message.reply(t("error.invalid_time"))
    splits.append(t)
    await state.update_data(splits=splits)
    if idx + 1 < len(segments):
        await state.update_data(idx=idx + 1)
        await message.answer(_segment_prompt(idx + 1, segments[idx + 1]))
        return
    await state.set_state(AddResult.waiting_for_comment)
    await message.answer(
        "Хочете додати нотатку до результату? Надішліть текст або натисніть «Пропустити».",
        reply_markup=get_comment_prompt_keyboard(),
    )


@router.message(AddResult.waiting_for_comment)
async def comment_received(
    message: types.Message,
    state: FSMContext,
    notifications: NotificationService,
    role_service: RoleService,
) -> None:
    """Save result together with supplied comment."""

    await _finalize_result_entry(
        message,
        message.from_user,
        state,
        message.text,
        notifications,
        role_service,
    )


@router.callback_query(F.data == "comment_skip", AddResult.waiting_for_comment)
async def comment_skipped(
    cb: types.CallbackQuery,
    state: FSMContext,
    notifications: NotificationService,
    role_service: RoleService,
) -> None:
    """Finalize result without comment."""

    await cb.answer("Без нотатки")
    await _finalize_result_entry(
        cb.message,
        cb.from_user,
        state,
        None,
        notifications,
        role_service,
    )


@router.callback_query(RepeatCB.filter())
async def repeat_previous(
    cb: types.CallbackQuery,
    callback_data: RepeatCB,
    notifications: NotificationService,
    role_service: RoleService,
) -> None:
    """Duplicate the previously saved result for faster logging."""

    key = (cb.from_user.id, callback_data.athlete_id)
    payload = LAST_RESULTS.get(key)
    if not payload:
        await cb.answer("Немає результату для повтору", show_alert=True)
        return

    await cb.answer()
    try:
        total, new_prs, timestamp, stats_payload = _persist_result(
            payload["athlete_id"],
            payload["athlete_name"],
            payload["stroke"],
            payload["dist"],
            payload["splits"],
            comment=None,
        )
    except Exception as exc:
        logging.error("Failed to repeat result: %s", exc, exc_info=True)
        await cb.message.answer(
            "Не вдалося повторити попередній результат. Спробуйте пізніше."
        )
        return

    dist = payload["dist"]
    txt = "🔁 Продубльовано попередній результат!\n" + _format_result_summary(
        dist, total, new_prs, stats_payload, None
    )

    keyboard = get_result_actions_keyboard(
        athlete_id=payload["athlete_id"],
        timestamp=timestamp,
        has_comment=False,
    )

    await cb.message.answer(txt, parse_mode="HTML", reply_markup=keyboard)

    analysis_text = _analysis_text(
        dist, payload["splits"], total, payload.get("segments")
    )
    await cb.message.answer(analysis_text, parse_mode="HTML")

    payload.update(timestamp=timestamp, comment="")

    trainers = await role_service.trainers_for_athlete(payload["athlete_id"])
    await notifications.notify_new_result(
        actor_id=cb.from_user.id,
        actor_name=cb.from_user.full_name,
        athlete_id=payload["athlete_id"],
        athlete_name=payload["athlete_name"],
        dist=payload["dist"],
        stroke=payload["stroke"],
        total=total,
        timestamp=timestamp,
        stats=stats_payload,
        trainers=trainers,
        new_prs=new_prs,
    )


@router.callback_query(CommentCB.filter(F.action == "edit"))
async def comment_edit(
    cb: types.CallbackQuery, callback_data: CommentCB, state: FSMContext
) -> None:
    """Prompt user to edit comment for a saved result."""

    timestamp = unpack_timestamp_from_callback(callback_data.ts)
    athlete_id = callback_data.athlete_id

    try:
        row_idx = _find_result_row(athlete_id, timestamp)
    except ValueError:
        await cb.answer("Результат не знайдено", show_alert=True)
        return

    try:
        current_comment = ws_results.cell(row_idx, COMMENT_COLUMN_INDEX).value or ""
    except Exception as exc:
        logging.error("Failed to load comment: %s", exc, exc_info=True)
        await cb.answer("Не вдалося завантажити нотатку", show_alert=True)
        return

    await state.set_state(AddResult.editing_comment)
    await state.update_data(
        edit_timestamp=timestamp,
        edit_athlete_id=athlete_id,
    )

    message_lines = ["Надішліть нову нотатку для результату."]
    if current_comment.strip():
        message_lines.append(f"Поточна нотатка: {current_comment.strip()}")
    else:
        message_lines.append("Зараз нотатки немає.")

    await cb.message.answer(
        "\n".join(message_lines),
        reply_markup=_build_comment_edit_keyboard(timestamp, athlete_id),
    )
    await cb.answer()


@router.message(AddResult.editing_comment)
async def save_comment_edit(message: types.Message, state: FSMContext) -> None:
    """Handle new comment text for existing result."""

    data = await state.get_data()
    timestamp = data.get("edit_timestamp")
    athlete_id = data.get("edit_athlete_id")
    if not timestamp or not athlete_id:
        await state.clear()
        await message.answer(
            "Не вдалося визначити результат. Спробуйте з меню історії."
        )
        return

    try:
        _update_comment(athlete_id, timestamp, message.text)
    except ValueError:
        await state.clear()
        await message.answer("Результат не знайдено. Спробуйте оновити історію.")
        return
    except Exception as exc:
        await state.clear()
        logging.error("Failed to update comment: %s", exc, exc_info=True)
        await message.answer("Не вдалося зберегти нотатку. Спробуйте пізніше.")
        return

    comment_clean = _normalize_comment(message.text)
    _sync_last_results(timestamp, comment_clean)
    await state.clear()
    await message.answer("Нотатку оновлено.")


@router.callback_query(CommentCB.filter(F.action == "clear"))
async def clear_comment(
    cb: types.CallbackQuery, callback_data: CommentCB, state: FSMContext
) -> None:
    """Remove comment from existing result."""

    timestamp = unpack_timestamp_from_callback(callback_data.ts)
    athlete_id = callback_data.athlete_id

    try:
        _update_comment(athlete_id, timestamp, None)
    except ValueError:
        await cb.answer("Результат не знайдено", show_alert=True)
        return
    except Exception as exc:
        logging.error("Failed to clear comment: %s", exc, exc_info=True)
        await cb.answer("Не вдалося видалити нотатку", show_alert=True)
        return

    _sync_last_results(timestamp, "")
    await state.clear()
    await cb.message.answer("Нотатку видалено.")
    await cb.answer()


@router.callback_query(F.data == "comment_cancel")
async def cancel_comment_edit(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel comment editing flow."""

    await state.clear()
    await cb.answer("Скасовано")
    await cb.message.answer("Редагування нотатки скасовано.")


@router.message(Command("results"))
async def cmd_results(message: types.Message) -> None:
    """Show latest results together with comments."""

    try:
        rows = ws_results.get_all_values()
    except Exception as exc:
        logging.error("Failed to load results: %s", exc, exc_info=True)
        await message.answer("Не вдалося завантажити результати. Спробуйте пізніше.")
        return

    if len(rows) <= 1:
        await message.answer("Поки немає збережених результатів.")
        return

    user_id = str(message.from_user.id)
    user_rows = [row for row in rows[1:] if row and str(row[0]) == user_id]
    if not user_rows:
        await message.answer("Для вас ще немає зафіксованих результатів.")
        return

    latest = list(reversed(user_rows[-5:]))
    blocks: list[str] = []
    for row in latest:
        try:
            dist = int(row[3])
            timestamp = row[4]
            total = float(str(row[6]).replace(",", "."))
            splits = json.loads(row[5]) if row[5] else []
        except (ValueError, json.JSONDecodeError, IndexError) as exc:
            logging.warning("Skipping malformed result row: %s (%s)", row, exc)
            continue

        block_lines = [f"<b>{timestamp}</b> — {dist} м, час {fmt_time(total)}"]
        comment = row[7].strip() if len(row) > 7 else ""
        if comment:
            block_lines.append(f"📝 {_comment_to_html(comment)}")
        if splits:
            block_lines.append(
                "Спліти: " + " • ".join(fmt_time(float(value)) for value in splits)
            )
        blocks.append("\n".join(block_lines))

    await message.answer(
        "\n\n".join(blocks) if blocks else "Не вдалося зчитати результати.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "history")
async def history(cb: types.CallbackQuery) -> None:
    """Show history of results for user."""

    try:
        rows = ws_results.get_all_values()[::-1]
        out = []
        processed_count = 0
        for row in rows:
            if row and str(row[0]) == str(cb.from_user.id):
                try:
                    dist = int(row[3])
                    splits = json.loads(row[5])
                    date = row[4]

                    out.append(f"<b>{date} | {dist} м:</b>")

                    for i, t in enumerate(splits):
                        try:
                            segment_speed = speed(get_segments(dist)[i], float(t))
                            out.append(
                                f"  - Відрізок {i+1}: {fmt_time(float(t))} (швидкість: {segment_speed:.2f} м/с)"
                            )
                        except IndexError:
                            out.append(
                                f"  - Відрізок {i+1}: {fmt_time(float(t))} (ПОМИЛКА: зайвий відрізок)"
                            )

                    if len(row) > 7 and row[7].strip():
                        out.append(
                            f"  📝 Нотатка: {_comment_to_html(row[7].strip())}"
                        )

                    out.append("-" * 20)
                    processed_count += 1

                except (ValueError, json.JSONDecodeError, IndexError) as e:
                    logging.warning(
                        "Skipping malformed row for user %s: %s. Error: %s",
                        cb.from_user.id,
                        row,
                        e,
                    )
                    continue

                if processed_count >= 10:
                    out.append("...")
                    break

        await cb.message.answer(
            "\n".join(out) if out else "Історія поки порожня.",
            parse_mode="HTML",
        )

    except Exception as e:
        logging.error(f"Critical error in history handler: {e}", exc_info=True)
        await cb.message.answer("Сталася критична помилка при завантаженні історії.")


@router.callback_query(F.data == "records")
async def records(cb: types.CallbackQuery) -> None:
    """Display personal records."""

    rows = ws_pr.get_all_values()
    best = {}
    for row in rows:
        try:
            uid, _, dist, _ = row[0].split("|")
            if int(uid) == cb.from_user.id:
                dist_key = int(dist)
                best.setdefault(dist_key, []).append(float(row[1].replace(",", ".")))
        except (ValueError, IndexError):
            continue

    if not best:
        return await cb.answer("Немає рекордів.")

    lines = []
    for dist, arr in sorted(best.items()):
        total = sum(arr)
        lines.append(
            f"🏅 {dist} м → {fmt_time(total)} (сума найкращих)\n"
            + " • ".join(fmt_time(t) for t in arr)
        )
    await cb.message.answer("\n\n".join(lines))


@router.callback_query(F.data == "menu_sprint")
async def menu_sprint(
    cb: types.CallbackQuery, state: FSMContext, role_service: RoleService
) -> None:
    """Show list of athletes for result entry."""

    try:
        records = ws_athletes.get_all_records()
    except Exception as e:
        logging.error(f"Failed to get athletes list: {e}")
        return await cb.message.answer(
            "Помилка: не вдалося отримати список спортсменів. Спробуйте пізніше."
        )

    parsed_records: list[tuple[int, str]] = []
    for rec in records:
        try:
            athlete_id = int(rec["ID"])
        except (KeyError, TypeError, ValueError):
            continue
        name = rec.get("Name", str(athlete_id))
        parsed_records.append((athlete_id, name))

    if parsed_records:
        await role_service.bulk_sync_athletes(parsed_records)

    role = await role_service.get_role(cb.from_user.id)
    if role == ROLE_ATHLETE:
        await state.update_data(athlete_id=cb.from_user.id)
        await cb.message.answer(
            "Оберіть дистанцію або введіть вручну:",
            reply_markup=get_distance_keyboard(),
        )
        await state.set_state(AddResult.choose_dist)
        await cb.answer()
        return

    accessible_ids = set(await role_service.get_accessible_athletes(cb.from_user.id))
    buttons = []
    for athlete_id, athlete_name in parsed_records:
        if accessible_ids and athlete_id not in accessible_ids:
            continue
        buttons.append(
            InlineKeyboardButton(
                text=athlete_name, callback_data=f"select_{athlete_id}"
            )
        )

    if not buttons:
        await cb.message.answer("Немає спортсменів, до яких у вас є доступ.")
        await cb.answer()
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[buttons])
    await cb.message.answer("Оберіть спортсмена:", reply_markup=kb)
    await state.set_state(AddResult.choose_athlete)
    await cb.answer()


@router.callback_query(F.data.startswith("select_"))
async def select_athlete(
    cb: types.CallbackQuery, state: FSMContext, role_service: RoleService
) -> None:
    """Save selected athlete and ask for distance."""

    try:
        athlete_id = int(cb.data.split("_", 1)[1])
    except ValueError:
        return await cb.message.answer("Помилка: ID спортсмена має бути числом.")
    if not await role_service.can_access_athlete(cb.from_user.id, athlete_id):
        await cb.answer("Немає доступу до цього спортсмена.", show_alert=True)
        return
    await state.update_data(athlete_id=athlete_id)
    await cb.message.answer(
        "Оберіть дистанцію або введіть вручну:",
        reply_markup=get_distance_keyboard(),
    )
    await state.set_state(AddResult.choose_dist)


@router.callback_query(F.data == "menu_history")
async def menu_history(cb: types.CallbackQuery) -> None:
    """Menu alias for history."""

    await history(cb)


@router.callback_query(F.data == "menu_records")
async def menu_records(cb: types.CallbackQuery) -> None:
    """Menu alias for records."""

    await records(cb)


@router.callback_query(F.data == "menu_stayer")
async def menu_stayer(cb: types.CallbackQuery) -> None:
    """Notify that stayer block is under construction."""

    await cb.message.answer("🚧 Блок «Стаєр» ще в розробці – скоро буде!")
