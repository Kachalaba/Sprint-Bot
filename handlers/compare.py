"""Handlers for team comparison analytics."""

from __future__ import annotations

from typing import Any

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

from i18n import t
from role_service import RoleService
from services import get_athletes_worksheet
from services.team_analytics_service import TeamAnalyticsService
from utils.logger import get_logger

router = Router()
logger = get_logger(__name__)
_TEAM_SERVICE = TeamAnalyticsService()


@router.message(Command(commands=["team_progress", "compare"]))
async def cmd_team_progress(message: types.Message, role_service: RoleService) -> None:
    """Generate comparison chart for selected athletes."""

    args = (message.text or "").split()[1:]
    if len(args) < 3:
        await message.answer(
            "Usage: /team_progress <stroke> <distance> <athlete_ids...> [group=G] [club=C]"
        )
        return

    stroke = args[0].lower()
    try:
        distance = int(args[1])
    except ValueError:
        await message.answer("Distance must be an integer value.")
        return

    athlete_ids: list[int] = []
    options: dict[str, str] = {}
    for token in args[2:]:
        if "=" in token:
            key, value = token.split("=", 1)
            options[key.strip().lower()] = value.strip()
            continue
        try:
            athlete_ids.append(int(token))
        except ValueError:
            await message.answer(t("error.invalid_id"))
            return

    if not athlete_ids:
        await message.answer(t("error.not_found"))
        return

    accessible = set(await role_service.get_accessible_athletes(message.from_user.id))
    if not set(athlete_ids).issubset(accessible):
        await message.answer(t("error.forbidden"))
        return

    profiles = _load_profiles()
    group_filter = options.get("group")
    club_filter = options.get("club")

    try:
        comparison = await _TEAM_SERVICE.compare_team(
            athlete_ids,
            stroke,
            distance,
            profiles=profiles,
            group=group_filter,
            club=club_filter,
        )
    except ValueError as exc:
        await message.answer(str(exc))
        return
    chart = await _TEAM_SERVICE.build_chart(comparison)
    caption = _TEAM_SERVICE.build_summary(comparison)

    await message.answer_photo(
        BufferedInputFile(chart, filename="team_comparison.png"),
        caption=caption,
    )


def _load_profiles() -> list[dict[str, Any]]:
    try:
        worksheet = get_athletes_worksheet()
        records = worksheet.get_all_records()
    except Exception as exc:  # pragma: no cover - external dependency
        logger.warning("Failed to load athlete profiles: %s", exc)
        return []

    profiles: list[dict[str, Any]] = []
    for record in records:
        athlete_id = _extract_int(record, "ID")
        if athlete_id is None:
            athlete_id = _extract_int(record, "athlete_id")
        if athlete_id is None:
            continue
        profiles.append(
            {
                "athlete_id": athlete_id,
                "group": record.get("Group") or record.get("group"),
                "club": record.get("Club") or record.get("club"),
            }
        )
    return profiles


def _extract_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["router"]
