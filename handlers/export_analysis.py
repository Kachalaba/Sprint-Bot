"""Handlers responsible for exporting PB/SoB analytics."""

from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

from i18n import t
from role_service import RoleService
from services.export_service import ExportService
from utils.logger import get_logger

router = Router()
logger = get_logger(__name__)
_EXPORT_SERVICE = ExportService()


@router.message(Command("export_analysis"))
async def cmd_export_analysis(
    message: types.Message, role_service: RoleService
) -> None:
    """Export PB/SoB dataset for accessible athletes."""

    tokens = (message.text or "").split()[1:]
    params = _parse_params(tokens)

    fmt = params.get("format", "csv").lower()
    stroke = params.get("stroke")
    distance = _parse_int(params.get("distance"))

    accessible = set(await role_service.get_accessible_athletes(message.from_user.id))
    ids_param = params.get("ids") or params.get("athletes")
    if ids_param:
        athlete_ids = [
            value for value in _parse_id_list(ids_param) if value in accessible
        ]
    else:
        athlete_ids = list(accessible)

    if not athlete_ids:
        await message.answer(t("error.not_found"))
        return

    try:
        payload = await _EXPORT_SERVICE.export_pb_sob(
            athlete_ids,
            stroke=stroke,
            distance=distance,
            fmt=fmt,
        )
    except ValueError as exc:
        await message.answer(str(exc))
        return

    ext = "xlsx" if fmt in {"xlsx", "excel"} else "csv"
    filename = f"pb_sob.{ext}"
    await message.answer_document(
        BufferedInputFile(payload, filename=filename),
        caption=t("export.ready"),
    )


def _parse_params(tokens: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        params[key.strip().lower()] = value.strip()
    return params


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_id_list(value: str) -> list[int]:
    result: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(int(item))
        except ValueError:
            continue
    return result


__all__ = ["router"]
