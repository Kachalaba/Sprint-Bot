"""Handlers for viewing personal records and Sum of Best metrics."""

from __future__ import annotations

import logging
from typing import Dict, Sequence, Tuple

from aiogram import Router, types
from aiogram.filters import Command

from i18n import t
from role_service import RoleService
from services import get_pr_worksheet, get_results_worksheet
from utils import fmt_time

router = Router()

RecordKey = Tuple[str, int]


def _collect_best_totals(athlete_id: int) -> Dict[RecordKey, float]:
    """Return best total time per (stroke, distance)."""

    try:
        worksheet = get_results_worksheet()
        rows = worksheet.get_all_values()
    except RuntimeError as exc:
        logging.error("Failed to access results worksheet: %s", exc, exc_info=True)
        return {}
    except Exception as exc:  # pragma: no cover - network dependent
        logging.error("Failed to load results for totals: %s", exc, exc_info=True)
        return {}

    totals: Dict[RecordKey, float] = {}
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
        if uid != athlete_id:
            continue
        try:
            total = float(str(total_raw).replace(",", "."))
        except (TypeError, ValueError):
            continue
        key = (stroke, dist)
        best = totals.get(key)
        if best is None or total < best:
            totals[key] = total
    return totals


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
