"""Handlers for viewing personal records and Sum of Best metrics."""

from __future__ import annotations

import logging
from typing import Dict, Tuple

from aiogram import Router, types
from aiogram.filters import Command

from role_service import RoleService
from services import ws_pr, ws_results
from utils import fmt_time

router = Router()

RecordKey = Tuple[str, int]


def _collect_best_totals(athlete_id: int) -> Dict[RecordKey, float]:
    """Return best total time per (stroke, distance)."""

    try:
        rows = ws_results.get_all_values()
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
        rows = ws_pr.get_all_values()
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
                await message.answer("Ідентифікатор спортсмена має бути числом.")
                return

    if not await role_service.can_access_athlete(message.from_user.id, target_id):
        await message.answer("У вас немає доступу до цього спортсмена.")
        return

    totals = _collect_best_totals(target_id)
    segment_bests = _collect_segment_bests(target_id)
    if not totals and not segment_bests:
        await message.answer("Поки немає рекордів для цього спортсмена.")
        return

    athlete_name = await _resolve_athlete_name(role_service, target_id)
    lines = [f"🏅 Рекорди для <b>{athlete_name}</b> ({target_id})"]

    keys = sorted(set(totals) | set(segment_bests), key=lambda item: (item[1], item[0]))
    for stroke, dist in keys:
        block: list[str] = [f"<b>{stroke}</b>, {dist} м"]
        best_total = totals.get((stroke, dist))
        if best_total is not None:
            block.append(f"• Загальний PR: {fmt_time(best_total)}")
        segments_map = segment_bests.get((stroke, dist)) or {}
        if segments_map:
            ordered_segments = [segments_map[idx] for idx in sorted(segments_map)]
            sob = sum(ordered_segments)
            block.append(f"• Sum of Best: {fmt_time(sob)}")
            block.append(
                "• Сегменти: "
                + ", ".join(fmt_time(value) for value in ordered_segments)
            )
        lines.append("\n".join(block))

    await message.answer("\n\n".join(lines), parse_mode="HTML")
