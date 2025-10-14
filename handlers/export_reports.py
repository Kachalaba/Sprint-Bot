"""Handlers for CSV/XLSX exports and analytical charts."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from i18n import t
from reports import (
    ExportFilters,
    ReportCache,
    build_cache_key,
    build_progress_chart,
    build_segment_speed_chart,
    export_results,
    load_results,
)
from role_service import RoleService

router = Router()
logger = logging.getLogger(__name__)
_CACHE = ReportCache()


@dataclass(slots=True)
class ParsedCommand:
    filters: ExportFilters
    errors: tuple[str, ...]


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_arguments(message: Message) -> ParsedCommand:
    text = message.text or ""
    parts = text.split()[1:]
    base = {
        "athlete_id": message.from_user.id if message.from_user else None,
        "stroke": None,
        "distance": None,
        "date_from": None,
        "date_to": None,
    }
    errors: list[str] = []
    for raw in parts:
        if "=" not in raw:
            errors.append(t("report.export.bad_token", token=raw))
            continue
        key, value = raw.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not value:
            errors.append(t("report.export.invalid_value", token=raw))
            continue
        if key in {"athlete", "athlete_id", "user", "uid"}:
            if value in {"me", "self"}:
                user = message.from_user
                athlete_id = user.id if user else None
                base["athlete_id"] = athlete_id
                continue
            try:
                base["athlete_id"] = int(value)
            except ValueError:
                errors.append(t("report.export.invalid_value", token=raw))
        elif key in {"stroke", "style"}:
            base["stroke"] = value.lower()
        elif key in {"distance", "dist"}:
            try:
                base["distance"] = int(value)
            except ValueError:
                errors.append(t("report.export.invalid_value", token=raw))
        elif key in {"from", "date_from", "start"}:
            try:
                base["date_from"] = _parse_iso_date(value)
            except ValueError:
                errors.append(t("report.export.invalid_value", token=raw))
        elif key in {"to", "date_to", "end"}:
            try:
                base["date_to"] = _parse_iso_date(value)
            except ValueError:
                errors.append(t("report.export.invalid_value", token=raw))
        else:
            errors.append(t("report.export.unknown_key", token=key))
    if (
        isinstance(base.get("date_from"), date)
        and isinstance(base.get("date_to"), date)
        and base["date_from"] > base["date_to"]
    ):
        errors.append(t("report.export.date_order"))
    filters = ExportFilters(**base)
    return ParsedCommand(filters=filters, errors=tuple(errors))


def _build_filename(fmt: str, filters: ExportFilters) -> str:
    athlete = filters.athlete_id or "all"
    distance = filters.distance or "any"
    stroke = filters.stroke or "any"
    suffix = fmt.lower()
    return f"export_{athlete}_{stroke}_{distance}.{suffix}"


async def _ensure_access(
    requester_id: int,
    filters: ExportFilters,
    role_service: RoleService,
) -> bool:
    target = filters.athlete_id or requester_id
    return await role_service.can_access_athlete(requester_id, target)


async def _send_export(
    message: Message,
    fmt: str,
    role_service: RoleService,
) -> None:
    parsed = _parse_arguments(message)
    if parsed.errors:
        await message.answer("\n".join(parsed.errors))
        return
    requester = 0
    if message.from_user:
        requester = message.from_user.id
    if not await _ensure_access(
        requester,
        parsed.filters,
        role_service,
    ):
        await message.answer(t("report.export.forbidden"))
        return
    cache_key = build_cache_key(
        parsed.filters,
        fmt=fmt,
        namespace="file",
    )
    extension = "xlsx" if fmt.lower() in {"xlsx", "excel"} else "csv"
    payload = await _CACHE.get(cache_key, extension)
    if payload is None:
        try:
            payload = await export_results(parsed.filters, fmt)
        except ValueError as exc:
            await message.answer(t("report.export.error", reason=str(exc)))
            return
        except Exception as exc:  # pragma: no cover - external deps
            logger.exception("Failed to generate export: %s", exc)
            await message.answer(t("report.export.unexpected"))
            return
        await _CACHE.set(cache_key, extension, payload)
    filename = _build_filename(extension, parsed.filters)
    document = BufferedInputFile(payload, filename=filename)
    await message.answer_document(
        document,
        caption=t("report.export.ready", fmt=extension),
    )


@router.message(Command("export_csv"))
async def cmd_export_csv(message: Message, role_service: RoleService) -> None:
    """Export sprint results to CSV."""

    await _send_export(message, "csv", role_service)


@router.message(Command("export_xlsx"))
async def cmd_export_xlsx(message: Message, role_service: RoleService) -> None:
    """Export sprint results to Excel."""

    await _send_export(message, "xlsx", role_service)


async def _generate_chart(
    cache_namespace: str,
    builder,
    filters: ExportFilters,
    *,
    extension: str,
) -> bytes:
    cache_key = build_cache_key(filters, fmt="png", namespace=cache_namespace)
    cached = await _CACHE.get(cache_key, extension)
    if cached is not None:
        return cached
    records = await load_results(filters)
    if not records:
        raise ValueError("no_results")
    distances = {record.distance for record in records}
    if len(distances) > 1:
        raise ValueError("mixed_distance")
    strokes = {record.stroke for record in records}
    if len(strokes) > 1:
        raise ValueError("mixed_stroke")
    try:
        image = await asyncio.to_thread(builder, records)
    except ValueError as exc:
        raise ValueError(str(exc))
    await _CACHE.set(cache_key, extension, image)
    return image


@router.message(Command("export_graphs"))
async def cmd_export_graphs(
    message: Message,
    role_service: RoleService,
) -> None:
    """Send cached analytical charts for selected filters."""

    parsed = _parse_arguments(message)
    if parsed.errors:
        await message.answer("\n".join(parsed.errors))
        return
    requester = message.from_user.id if message.from_user else 0
    if not await _ensure_access(requester, parsed.filters, role_service):
        await message.answer(t("report.export.forbidden"))
        return
    try:
        speed_chart = await _generate_chart(
            "chart_speed",
            build_segment_speed_chart,
            parsed.filters,
            extension="png",
        )
        progress_chart = await _generate_chart(
            "chart_progress",
            build_progress_chart,
            parsed.filters,
            extension="png",
        )
    except ValueError as exc:
        reason = str(exc)
        if reason == "no_results":
            await message.answer(t("report.export.no_results"))
        elif reason == "mixed_distance":
            await message.answer(t("report.export.mixed_distance"))
        elif reason == "mixed_stroke":
            await message.answer(t("report.export.mixed_stroke"))
        else:
            await message.answer(t("report.export.chart_error", reason=reason))
        return
    except Exception as exc:  # pragma: no cover - external deps
        logger.exception("Failed to render export charts: %s", exc)
        await message.answer(t("report.export.unexpected"))
        return
    await message.answer_photo(
        BufferedInputFile(speed_chart, filename="segments.png"),
        caption=t("report.export.speed_caption"),
    )
    await message.answer_photo(
        BufferedInputFile(progress_chart, filename="progress.png"),
        caption=t("report.export.progress_caption"),
    )
    await message.answer(t("report.export.graphs_ready"))
