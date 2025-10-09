"""Handlers for generating graphical sprint reports."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Sequence

from aiogram import Router, types
from aiogram.enums import MessageEntityType
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from i18n import t
from reports import AttemptReport, SegmentReportRow, generate_image_report
from role_service import RoleService
from services import get_pr_worksheet, get_results_worksheet
from utils import get_segments

router = Router()


_ERROR_TRANSLATION_KEYS: dict[str, str] = {
    "mention": "report.errors.mention",
    "invalid_id": "report.errors.invalid_id",
    "forbidden": "report.errors.forbidden",
    "no_results": "report.errors.no_results",
    "empty_report": "report.errors.empty_report",
}


def build_report_error(reason: str) -> str:
    """Return localized error message for report commands."""

    try:
        key = _ERROR_TRANSLATION_KEYS[reason]
    except KeyError as exc:  # pragma: no cover - defensive branch
        raise ValueError(f"Unknown report error reason: {reason}") from exc
    return t(key)


def build_report_caption(distance: int, stroke: str) -> str:
    """Return localized caption for the report image."""

    return t("report.caption.last", distance=distance, stroke=stroke)


@dataclass(frozen=True)
class ResultPayload:
    """Parsed representation of a sprint attempt."""

    athlete_id: int
    athlete_name: str
    stroke: str
    distance: int
    timestamp: str
    splits: Sequence[float]
    total: float


def _resolve_target_id(message: Message) -> tuple[int, str | None]:
    """Extract target athlete id from command message."""

    entities = message.entities or []
    for entity in entities:
        if entity.type is MessageEntityType.TEXT_MENTION and entity.user:
            return entity.user.id, None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1:
        return message.from_user.id, None
    arg = parts[1].strip()
    if not arg:
        return message.from_user.id, None
    if arg.startswith("@"):
        return message.from_user.id, build_report_error("mention")
    try:
        return int(arg), None
    except ValueError:
        return message.from_user.id, build_report_error("invalid_id")


def _parse_row(row: Sequence[str]) -> ResultPayload | None:
    """Parse worksheet row into a :class:`ResultPayload`."""

    if not row or len(row) < 7:
        return None
    try:
        athlete_id = int(row[0])
        athlete_name = row[1]
        stroke = str(row[2])
        distance = int(row[3])
        timestamp = str(row[4])
        splits_raw = row[5]
        total_raw = row[6]
    except (ValueError, TypeError, IndexError):
        return None
    try:
        splits = json.loads(splits_raw) if splits_raw else []
    except json.JSONDecodeError:
        return None
    try:
        splits = [float(str(value).replace(",", ".")) for value in splits]
        total = float(str(total_raw).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return ResultPayload(
        athlete_id=athlete_id,
        athlete_name=athlete_name,
        stroke=stroke,
        distance=distance,
        timestamp=timestamp,
        splits=splits,
        total=total,
    )


def _load_last_result(athlete_id: int) -> ResultPayload | None:
    """Return latest attempt for the athlete."""

    try:
        worksheet = get_results_worksheet()
        rows = worksheet.get_all_values()
    except RuntimeError as exc:
        logging.error("Failed to access results worksheet: %s", exc, exc_info=True)
        return None
    except Exception as exc:  # pragma: no cover - network dependent
        logging.error("Failed to load results: %s", exc, exc_info=True)
        return None
    latest: ResultPayload | None = None
    for row in rows[1:]:
        payload = _parse_row(row)
        if payload is None or payload.athlete_id != athlete_id:
            continue
        if latest is None or payload.timestamp > latest.timestamp:
            latest = payload
    return latest


def _load_best_total(athlete_id: int, stroke: str, distance: int) -> float | None:
    """Return best total time for an athlete stroke/distance pair."""

    try:
        worksheet = get_results_worksheet()
        rows = worksheet.get_all_values()
    except RuntimeError as exc:
        logging.error("Failed to access results worksheet: %s", exc, exc_info=True)
        return None
    except Exception as exc:  # pragma: no cover - network dependent
        logging.error("Failed to load totals: %s", exc, exc_info=True)
        return None
    best: float | None = None
    for row in rows[1:]:
        payload = _parse_row(row)
        if payload is None:
            continue
        if (
            payload.athlete_id != athlete_id
            or payload.stroke != stroke
            or payload.distance != distance
        ):
            continue
        if best is None or payload.total < best:
            best = payload.total
    return best


def _load_segment_bests(
    athlete_id: int, stroke: str, distance: int, segments_count: int
) -> list[tuple[float | None, str | None]]:
    """Return best split per segment together with their timestamps."""

    try:
        worksheet = get_pr_worksheet()
        rows = worksheet.get_all_values()
    except RuntimeError as exc:
        logging.error("Failed to access PR worksheet: %s", exc, exc_info=True)
        return [(None, None)] * segments_count
    except Exception as exc:  # pragma: no cover - network dependent
        logging.error("Failed to load segment PRs: %s", exc, exc_info=True)
        return [(None, None)] * segments_count
    values: dict[int, tuple[float, str | None]] = {}
    for row in rows:
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
        if uid != athlete_id or stroke_key != stroke or dist_val != distance:
            continue
        try:
            value = float(str(row[1]).replace(",", "."))
        except (TypeError, ValueError):
            continue
        timestamp = str(row[2]) if len(row) > 2 and row[2] else None
        values[seg_idx] = (value, timestamp)
    result: list[tuple[float | None, str | None]] = []
    for idx in range(segments_count):
        result.append(values.get(idx, (None, None)))
    return result


def _resolve_segment_lengths(distance: int, segments_count: int) -> Sequence[float]:
    """Return best-guess segment lengths for report visualisation."""

    if segments_count <= 0:
        return []
    defaults = [float(seg) for seg in get_segments(distance)]
    if len(defaults) == segments_count:
        return defaults
    average = distance / segments_count if distance else 0
    return [float(average)] * segments_count


@router.message(Command("report_last"))
async def cmd_report_last(message: types.Message, role_service: RoleService) -> None:
    """Generate image summary for the latest attempt."""

    target_id, error = _resolve_target_id(message)
    if error:
        await message.answer(error)
        return
    if not await role_service.can_access_athlete(message.from_user.id, target_id):
        await message.answer(build_report_error("forbidden"))
        return

    payload = _load_last_result(target_id)
    if payload is None:
        await message.answer(build_report_error("no_results"))
        return

    lengths = _resolve_segment_lengths(payload.distance, len(payload.splits))
    segment_bests = _load_segment_bests(
        payload.athlete_id, payload.stroke, payload.distance, len(payload.splits)
    )
    rows: list[SegmentReportRow] = []
    for idx, split in enumerate(payload.splits):
        distance = lengths[idx] if idx < len(lengths) else lengths[-1] if lengths else 0
        best_value = segment_bests[idx][0] if idx < len(segment_bests) else None
        rows.append(SegmentReportRow(time=split, distance=distance, best=best_value))

    sob_flag = any(
        ts and ts == payload.timestamp for _, ts in segment_bests[: len(payload.splits)]
    )
    best_total = _load_best_total(payload.athlete_id, payload.stroke, payload.distance)
    total_flag = best_total is not None and abs(payload.total - best_total) <= 1e-6

    attempt = AttemptReport(
        athlete_name=payload.athlete_name or f"ID {payload.athlete_id}",
        stroke=payload.stroke,
        distance=payload.distance,
        timestamp=payload.timestamp,
        total_time=payload.total,
        segments=rows,
        total_is_pr=total_flag,
        sob_improved=sob_flag,
    )
    try:
        image_bytes = generate_image_report(attempt)
    except ValueError:
        await message.answer(build_report_error("empty_report"))
        return
    except RuntimeError as exc:  # pragma: no cover - matplotlib backend issues
        logging.error("Failed to generate sprint image report: %s", exc, exc_info=True)
        await message.answer(
            "⚠️ Failed to render the graphical report. Please try again later."
        )
        return

    file = BufferedInputFile(image_bytes, filename="report.png")
    await message.answer_photo(
        file,
        caption=build_report_caption(payload.distance, payload.stroke),
    )
