"""Handlers for viewing personal records and Sum of Best metrics."""

from __future__ import annotations

import logging
from typing import Dict, Iterable, Sequence, Tuple

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

from i18n import t
from keyboards import AnalysisCB
from role_service import ROLE_ADMIN, RoleService
from services import get_pr_worksheet, get_results_worksheet
from services.export_service import ExportService
from utils import fmt_time

router = Router()

RecordKey = Tuple[str, int]


_EXPORT_SERVICE = ExportService()


def _collect_best_totals_bulk(
    athlete_ids: Iterable[int],
) -> Dict[int, Dict[RecordKey, float]]:
    """Return mapping of athlete id to their best totals."""

    ids = {int(value) for value in athlete_ids}
    if not ids:
        return {}

    try:
        worksheet = get_results_worksheet()
        rows = worksheet.get_all_values()
    except RuntimeError as exc:
        logging.error("Failed to access results worksheet: %s", exc, exc_info=True)
        return {}
    except Exception as exc:  # pragma: no cover - network dependent
        logging.error("Failed to load results for totals: %s", exc, exc_info=True)
        return {}

    totals_map: Dict[int, Dict[RecordKey, float]] = {
        athlete_id: {} for athlete_id in ids
    }
    for row in rows:
        if not row or len(row) < 7:
            continue
        try:
            uid = int(row[0])
            stroke = str(row[2])
            dist = int(row[3])
            total_raw = row[6]
        except (ValueError, TypeError, IndexError):
            continue
        if uid not in totals_map:
            continue
        try:
            total = float(str(total_raw).replace(",", "."))
        except (TypeError, ValueError):
            continue
        key = (stroke, dist)
        athlete_totals = totals_map[uid]
        best = athlete_totals.get(key)
        if best is None or total < best:
            athlete_totals[key] = total
    return totals_map


def _collect_best_totals(athlete_id: int) -> Dict[RecordKey, float]:
    """Return best total time per (stroke, distance)."""

    return _collect_best_totals_bulk((athlete_id,)).get(athlete_id, {})


def _collect_segment_bests(athlete_id: int) -> Dict[RecordKey, Dict[int, float]]:
    """Return best segment times grouped by stroke and distance."""

    try:
        worksheet = get_pr_worksheet()
        rows = worksheet.get_all_values()
    except RuntimeError as exc:
        logging.error("Failed to access PR worksheet: %s", exc, exc_info=True)
        return {}
    except Exception as exc:  # pragma: no cover - network dependent
        logging.error("Failed to load segment PRs: %s", exc, exc_info=True)
        return {}

    segments: Dict[RecordKey, Dict[int, float]] = {}
    for row in rows:
        if not row or len(row) < 2:
            continue
        key_raw = row[0]
        try:
            uid_str, stroke, dist_str, seg_idx_str = key_raw.split("|")
            uid = int(uid_str)
            dist = int(dist_str)
            seg_idx = int(seg_idx_str)
        except (ValueError, AttributeError):
            continue
        if uid != athlete_id:
            continue
        try:
            value = float(str(row[1]).replace(",", "."))
        except (TypeError, ValueError):
            continue
        record_key = (stroke, dist)
        segments.setdefault(record_key, {})[seg_idx] = value
    return segments


async def _resolve_athlete_name(role_service: RoleService, athlete_id: int) -> str:
    """Try to resolve athlete's full name via role service."""

    users = await role_service.list_users(roles=None)
    for user in users:
        if user.telegram_id == athlete_id and user.full_name:
            return user.full_name
    return f"ID {athlete_id}"


def _format_pb_summary(
    totals: Dict[RecordKey, float], athlete_name: str, athlete_id: int
) -> str:
    """Return localized PB summary text."""

    if not totals:
        return t("analysis.messages.no_pb")

    lines = [t("analysis.messages.pb_header", name=athlete_name, id=athlete_id)]
    for (stroke, distance), value in sorted(
        totals.items(), key=lambda item: (item[0][1], item[0][0])
    ):
        lines.append(
            t(
                "analysis.messages.pb_entry",
                stroke=stroke,
                distance=distance,
                total=fmt_time(value),
            )
        )
    return "\n".join(lines)


def _format_sob_summary(
    segments: Dict[RecordKey, Dict[int, float]], athlete_name: str, athlete_id: int
) -> str:
    """Return localized Sum of Best summary text."""

    entries: list[str] = []
    for (stroke, distance), parts in sorted(
        segments.items(), key=lambda item: (item[0][1], item[0][0])
    ):
        if not parts:
            continue
        ordered = [parts[idx] for idx in sorted(parts)]
        sob_value = sum(ordered)
        splits = " • ".join(fmt_time(value) for value in ordered)
        entries.append(
            t(
                "analysis.messages.sob_entry",
                stroke=stroke,
                distance=distance,
                sob=fmt_time(sob_value),
                splits=splits,
            )
        )

    if not entries:
        return t("analysis.messages.no_sob")

    header = t("analysis.messages.sob_header", name=athlete_name, id=athlete_id)
    return "\n".join([header, *entries])


def _build_team_comparison(
    athlete_id: int, athlete_name: str, peer_ids: Iterable[int]
) -> str:
    """Return comparison summary for athlete versus peers."""

    ids = set(peer_ids)
    ids.add(athlete_id)
    totals_map = _collect_best_totals_bulk(ids)
    target_totals = totals_map.get(athlete_id) or {}
    if not target_totals:
        return t("analysis.messages.no_pb")

    peer_dataset = [
        totals_map.get(peer_id, {}) for peer_id in ids if peer_id != athlete_id
    ]
    if not peer_dataset:
        return t("analysis.messages.compare_no_peers")

    lines = [t("analysis.messages.compare_header", name=athlete_name, id=athlete_id)]
    has_comparisons = False
    for (stroke, distance), value in sorted(
        target_totals.items(), key=lambda item: (item[0][1], item[0][0])
    ):
        peer_values = [
            dataset[(stroke, distance)]
            for dataset in peer_dataset
            if (stroke, distance) in dataset
        ]
        if not peer_values:
            continue
        average = sum(peer_values) / len(peer_values)
        delta = average - value
        if delta < -0.01:
            delta_text = t(
                "analysis.messages.compare_better", delta=fmt_time(abs(delta))
            )
        elif delta > 0.01:
            delta_text = t("analysis.messages.compare_slower", delta=fmt_time(delta))
        else:
            delta_text = t("analysis.messages.compare_equal")
        lines.append(
            t(
                "analysis.messages.compare_entry",
                stroke=stroke,
                distance=distance,
                athlete=fmt_time(value),
                team=fmt_time(average),
                delta=delta_text,
            )
        )
        has_comparisons = True

    if not has_comparisons:
        return t("analysis.messages.compare_no_peers")

    return "\n".join(lines)


def format_result_card(
    stroke: str,
    distance: int,
    *,
    date: str | None = None,
    total: float | None = None,
    sob: float | None = None,
    splits: Sequence[float] | None = None,
) -> str:
    """Compose localized card text for a single result entry."""

    lines = [
        t("res.card.style", style=stroke),
        t("res.card.distance", distance=distance),
    ]
    if date:
        lines.append(t("res.card.date", date=date))
    if total is not None:
        lines.append(t("res.card.total", total=fmt_time(total)))
    if sob is not None:
        lines.append(t("res.card.sob", sob=fmt_time(sob)))
    if splits:
        formatted_splits = ", ".join(fmt_time(value) for value in splits)
        lines.append(t("res.card.splits", splits=formatted_splits))
    return "\n".join(lines)


@router.message(Command("best"))
async def cmd_best(message: types.Message, role_service: RoleService) -> None:
    """Display personal records and Sum of Best for an athlete."""

    args = (message.text or "").split(maxsplit=1)
    target_id = message.from_user.id
    if len(args) > 1:
        value = args[1].strip()
        if value:
            try:
                target_id = int(value)
            except ValueError:
                await message.answer(t("res.invalid_id"))
                return

    if not await role_service.can_access_athlete(message.from_user.id, target_id):
        await message.answer(t("error.forbidden"))
        return

    totals = _collect_best_totals(target_id)
    segment_bests = _collect_segment_bests(target_id)
    if not totals and not segment_bests:
        await message.answer(t("error.not_found"))
        return

    athlete_name = await _resolve_athlete_name(role_service, target_id)
    lines = [t("res.card.title", name=athlete_name, id=target_id)]

    keys = sorted(set(totals) | set(segment_bests), key=lambda item: (item[1], item[0]))
    for stroke, dist in keys:
        best_total = totals.get((stroke, dist))
        segments_map = segment_bests.get((stroke, dist)) or {}
        ordered_segments = (
            [segments_map[idx] for idx in sorted(segments_map)]
            if segments_map
            else None
        )
        sob_value = sum(ordered_segments) if ordered_segments else None
        block_text = format_result_card(
            stroke,
            dist,
            total=best_total,
            sob=sob_value,
            splits=ordered_segments,
        )
        lines.append(block_text)

    await message.answer("\n\n".join(lines), parse_mode="HTML")


@router.message(Command("show_sob"))
async def cmd_show_sob(message: types.Message, role_service: RoleService) -> None:
    """Display Sum of Best metrics for selected athlete."""

    tokens = (message.text or "").split()[1:]
    target_id = message.from_user.id
    if tokens:
        try:
            target_id = int(tokens[0])
        except ValueError:
            await message.answer(t("res.invalid_id"))
            return

    if not await role_service.can_access_athlete(message.from_user.id, target_id):
        await message.answer(t("error.forbidden"))
        return

    segments = _collect_segment_bests(target_id)
    athlete_name = await _resolve_athlete_name(role_service, target_id)
    text = _format_sob_summary(segments, athlete_name, target_id)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("export_pb"))
async def cmd_export_pb(message: types.Message, role_service: RoleService) -> None:
    """Export PB/SoB dataset for a specific athlete."""

    tokens = (message.text or "").split()[1:]
    target_id = message.from_user.id
    fmt = "csv"

    if tokens:
        first = tokens[0].lower()
        if first in {"csv", "xlsx", "excel"}:
            fmt = first
            tokens = tokens[1:]
        else:
            try:
                target_id = int(tokens[0])
            except ValueError:
                await message.answer(t("res.invalid_id"))
                return
            tokens = tokens[1:]

    if tokens:
        fmt_candidate = tokens[0].lower()
        if fmt_candidate in {"csv", "xlsx", "excel"}:
            fmt = fmt_candidate
        else:
            await message.answer(t("analysis.messages.invalid_format", fmt=tokens[0]))
            return

    if not await role_service.can_access_athlete(message.from_user.id, target_id):
        await message.answer(t("error.forbidden"))
        return

    try:
        payload = await _EXPORT_SERVICE.export_pb_sob([target_id], fmt=fmt)
    except ValueError as exc:
        await message.answer(str(exc))
        return

    ext = "xlsx" if fmt in {"xlsx", "excel"} else "csv"
    filename = f"pb_sob_{target_id}.{ext}"
    document = BufferedInputFile(payload, filename=filename)
    await message.answer_document(document, caption=t("export.ready"))


@router.callback_query(AnalysisCB.filter())
async def handle_analysis_callback(
    cb: types.CallbackQuery, callback_data: AnalysisCB, role_service: RoleService
) -> None:
    """Handle inline analytics shortcuts for athletes."""

    athlete_id = callback_data.athlete_id
    if not await role_service.can_access_athlete(cb.from_user.id, athlete_id):
        await cb.answer(t("error.forbidden"), show_alert=True)
        return

    action = callback_data.action
    athlete_name = await _resolve_athlete_name(role_service, athlete_id)

    async def _send_text(text: str, *, html: bool = False) -> None:
        if cb.message:
            await cb.message.answer(text, parse_mode="HTML" if html else None)
        else:  # pragma: no cover - defensive branch
            await cb.bot.send_message(
                cb.from_user.id, text, parse_mode="HTML" if html else None
            )

    if action == "pb":
        totals = _collect_best_totals(athlete_id)
        await _send_text(
            _format_pb_summary(totals, athlete_name, athlete_id), html=True
        )
        await cb.answer()
        return

    if action == "sob":
        segments = _collect_segment_bests(athlete_id)
        await _send_text(
            _format_sob_summary(segments, athlete_name, athlete_id), html=True
        )
        await cb.answer()
        return

    if action == "compare":
        accessible = set(await role_service.get_accessible_athletes(cb.from_user.id))
        accessible.discard(athlete_id)
        text = _build_team_comparison(athlete_id, athlete_name, accessible)
        await _send_text(text, html=True)
        await cb.answer()
        return

    if action == "export":
        try:
            payload = await _EXPORT_SERVICE.export_pb_sob([athlete_id])
        except ValueError as exc:
            await cb.answer(str(exc), show_alert=True)
            return
        document = BufferedInputFile(payload, filename=f"pb_sob_{athlete_id}.csv")
        if cb.message:
            await cb.message.answer_document(document, caption=t("export.ready"))
        else:  # pragma: no cover - defensive branch
            await cb.bot.send_document(
                cb.from_user.id, document, caption=t("export.ready")
            )
        await cb.answer()
        return

    requester_role = await role_service.get_role(cb.from_user.id)
    if requester_role != ROLE_ADMIN:
        await cb.answer(t("error.forbidden"), show_alert=True)
        return

    if action == "simulate":
        await _send_text(
            t("analysis.messages.simulate_hint", command=f"/test_athlete {athlete_id}"),
            html=True,
        )
        await cb.answer()
        return

    if action == "admin":
        await _send_text(t("analysis.messages.admin_hint"), html=True)
        await cb.answer()
        return

    await cb.answer(t("analysis.messages.unknown_action"), show_alert=True)
