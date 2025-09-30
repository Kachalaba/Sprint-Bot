from __future__ import annotations

import io
import logging
from collections import defaultdict
from datetime import datetime
from typing import Iterable

import matplotlib
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from role_service import ROLE_ATHLETE, RoleService
from services import ws_athletes, ws_results
from utils import fmt_time

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  # isort:skip

router = Router()
logger = logging.getLogger(__name__)


def _extract_athlete_id(record: dict) -> int | None:
    """Safely parse athlete id from worksheet record."""

    try:
        raw_id = record.get("ID")
    except AttributeError:  # pragma: no cover - defensive
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def _chunked(
    iterable: Iterable[InlineKeyboardButton], size: int = 2
) -> list[list[InlineKeyboardButton]]:
    """Split buttons into rows of given size."""

    row: list[InlineKeyboardButton] = []
    keyboard: list[list[InlineKeyboardButton]] = []
    for button in iterable:
        row.append(button)
        if len(row) == size:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return keyboard


def _format_progress_table(distances: dict[int, list[tuple[datetime, float]]]) -> str:
    """Return formatted HTML table with improvements per distance."""

    header = "Дистанція | Перший час | Поточний | Δ"
    lines = [header, "-" * len(header)]
    for dist, entries in sorted(distances.items()):
        first = entries[0][1]
        last = entries[-1][1]
        delta = first - last
        trend = "↓" if delta > 0 else ("↑" if delta < 0 else "=")
        lines.append(
            "{dist} м | {first} | {last} | {trend} {delta:.2f} c".format(
                dist=dist,
                first=fmt_time(first),
                last=fmt_time(last),
                trend=trend,
                delta=abs(delta),
            )
        )
    return "<pre>{}</pre>".format("\n".join(lines))


def _build_athletes_keyboard(records: list[dict]) -> InlineKeyboardMarkup:
    """Create an inline keyboard with athlete choices."""

    buttons = []
    for rec in records:
        athlete_id = _extract_athlete_id(rec)
        if athlete_id is None:
            fallback = rec.get("athlete_id") or rec.get("id")
            try:
                athlete_id = int(fallback) if fallback is not None else None
            except (TypeError, ValueError):
                athlete_id = None
        name = rec.get("Name") or rec.get("name") or str(athlete_id)
        if not athlete_id:
            continue
        buttons.append(
            InlineKeyboardButton(
                text=name,
                callback_data=f"progress_select_{athlete_id}",
            )
        )
    if not buttons:
        raise ValueError("No valid athletes in worksheet")
    return InlineKeyboardMarkup(inline_keyboard=_chunked(buttons, size=2))


def _parse_results(
    raw_rows: list[list[str]], athlete_id: str
) -> dict[int, list[tuple[datetime, float]]]:
    """Group athlete results by distance."""

    grouped: dict[int, list[tuple[datetime, float]]] = defaultdict(list)
    for row in raw_rows:
        if len(row) < 7:
            continue
        if str(row[0]) != athlete_id:
            continue
        try:
            dist = int(row[3])
            timestamp = datetime.fromisoformat(row[4])
            total = float(str(row[6]).replace(",", "."))
        except (ValueError, IndexError):
            logger.warning("Skipping malformed result row: %s", row)
            continue
        grouped[dist].append((timestamp, total))

    for entries in grouped.values():
        entries.sort(key=lambda item: item[0])
    return grouped


def _build_progress_plot(
    distances: dict[int, list[tuple[datetime, float]]], athlete_name: str
) -> bytes:
    """Render progress plot and return PNG bytes."""

    fig, ax = plt.subplots(figsize=(10, 6))
    for dist, entries in sorted(distances.items()):
        dates = [ts for ts, _ in entries]
        totals = [total for _, total in entries]
        ax.plot(dates, totals, marker="o", label=f"{dist} м")

    ax.set_title(f"Прогрес спортсмена {athlete_name}")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Час, с")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()
    fig.autofmt_xdate()

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


async def _send_progress_report(
    event: types.Message | types.CallbackQuery, athlete_id: int
) -> None:
    """Render progress for athlete and send to requester."""

    try:
        raw_rows = ws_results.get_all_values()
    except Exception as exc:  # pragma: no cover - external service
        logger.error("Failed to load results: %s", exc, exc_info=True)
        target = event.message if isinstance(event, types.CallbackQuery) else event
        await target.answer("Не вдалося завантажити результати. Спробуйте пізніше.")
        if isinstance(event, types.CallbackQuery):
            await event.answer()
        return

    if len(raw_rows) <= 1:
        target = event.message if isinstance(event, types.CallbackQuery) else event
        await target.answer("Для цього спортсмена ще немає результатів.")
        if isinstance(event, types.CallbackQuery):
            await event.answer()
        return

    athlete_key = str(athlete_id)
    distances = _parse_results(raw_rows[1:], athlete_key)
    if not distances:
        target = event.message if isinstance(event, types.CallbackQuery) else event
        await target.answer("Для цього спортсмена ще немає результатів.")
        if isinstance(event, types.CallbackQuery):
            await event.answer()
        return

    athlete_name = next(
        (row[1] for row in raw_rows[1:] if str(row[0]) == athlete_key and row[1]),
        "спортсмен",
    )

    image_bytes = _build_progress_plot(distances, athlete_name)
    table_text = _format_progress_table(distances)

    target = event.message if isinstance(event, types.CallbackQuery) else event
    await target.answer_photo(
        BufferedInputFile(image_bytes, filename=f"progress_{athlete_key}.png"),
        caption=f"📈 Прогрес для {athlete_name}",
    )
    await target.answer(
        "<b>Динаміка за дистанціями</b>\n" + table_text,
        parse_mode="HTML",
    )
    if isinstance(event, types.CallbackQuery):
        await event.answer()


@router.message(Command("progress"))
async def cmd_progress(message: types.Message, role_service: RoleService) -> None:
    """Ask to choose athlete for progress visualization."""

    await role_service.upsert_user(message.from_user)
    role = await role_service.get_role(message.from_user.id)
    if role == ROLE_ATHLETE:
        await _send_progress_report(message, message.from_user.id)
        return

    try:
        records = ws_athletes.get_all_records()
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.error("Failed to load athletes: %s", exc, exc_info=True)
        await message.answer(
            "Не вдалося отримати список спортсменів. Спробуйте пізніше."
        )
        return

    accessible_ids = set(
        await role_service.get_accessible_athletes(message.from_user.id)
    )
    filtered = [
        rec
        for rec in records
        if (athlete_id := _extract_athlete_id(rec)) is not None
        and (not accessible_ids or athlete_id in accessible_ids)
    ]

    await role_service.bulk_sync_athletes(
        [
            (
                athlete_id,
                rec.get("Name", str(athlete_id)),
            )
            for rec in filtered
            if (athlete_id := _extract_athlete_id(rec)) is not None
        ]
    )

    if not filtered:
        await message.answer("Поки немає зареєстрованих спортсменів.")
        return

    try:
        keyboard = _build_athletes_keyboard(filtered)
    except ValueError:
        await message.answer("Не знайдено жодного валідного спортсмена у таблиці.")
        return

    await message.answer(
        "Оберіть спортсмена для перегляду прогресу:", reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("progress_select_"))
async def show_progress(cb: types.CallbackQuery, role_service: RoleService) -> None:
    """Generate progress visualization for selected athlete."""

    try:
        athlete_id = int(cb.data.split("_", 2)[-1])
    except ValueError:
        await cb.answer("Некоректний ідентифікатор.", show_alert=True)
        return

    if not await role_service.can_access_athlete(cb.from_user.id, athlete_id):
        await cb.answer("Немає доступу до цього спортсмена.", show_alert=True)
        return

    await _send_progress_report(cb, athlete_id)
