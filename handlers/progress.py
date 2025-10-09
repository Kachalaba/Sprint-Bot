from __future__ import annotations

import asyncio
import io
import logging
import os
from collections import OrderedDict, defaultdict
from datetime import datetime
from typing import Iterable, Sequence

import matplotlib
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from role_service import ROLE_ATHLETE, RoleService
from services import get_athletes_worksheet, get_results_worksheet
from services.stats_service import StatsPeriod, StatsService, TurnProgressResult
from utils import fmt_time

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  # isort:skip


_SUPPORTED_TURN_STROKES = ("breaststroke", "butterfly")
_STROKE_ALIASES = {
    "breast": "breaststroke",
    "breaststroke": "breaststroke",
    "breastroke": "breaststroke",
    "breast-stroke": "breaststroke",
    "br": "breaststroke",
    "брас": "breaststroke",
    "брасс": "breaststroke",
    "butterfly": "butterfly",
    "fly": "butterfly",
    "баттерфляй": "butterfly",
    "дельфин": "butterfly",
    "батерфляй": "butterfly",
    "bf": "butterfly",
}
_STROKE_TITLES = {
    "breaststroke": "Брасс",
    "butterfly": "Баттерфляй",
}

_DEFAULT_TURN_STROKE = (
    os.getenv("TURN_ANALYSIS_DEFAULT_STROKE", "breaststroke").strip().lower()
)
if _DEFAULT_TURN_STROKE not in _SUPPORTED_TURN_STROKES:
    _DEFAULT_TURN_STROKE = "breaststroke"

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

    return _figure_to_png(fig)


def _figure_to_png(fig: plt.Figure) -> bytes:
    """Serialize matplotlib figure into PNG bytes."""

    buf = io.BytesIO()
    try:
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=150)
    except Exception as exc:  # pragma: no cover - matplotlib backend issues
        logger.exception("Failed to render matplotlib figure: %s", exc)
        raise RuntimeError("Failed to render matplotlib figure") from exc
    finally:
        plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _normalize_stroke(value: str | None) -> str | None:
    """Return canonical stroke identifier or ``None`` if unsupported."""

    if not value:
        return None
    lookup = value.strip().lower()
    return _STROKE_ALIASES.get(lookup)


def _stroke_title(value: str) -> str:
    """Return human-readable stroke label for progress messages."""

    return _STROKE_TITLES.get(value, value.title())


def _group_turn_sessions(rows: Sequence[dict]) -> list[dict]:
    """Group raw turn rows by training session preserving order."""

    sessions: OrderedDict[int, dict] = OrderedDict()
    for row in rows:
        session = sessions.setdefault(
            row["result_id"],
            {
                "timestamp": row["timestamp"],
                "distance": row["distance"],
                "turns": [],
            },
        )
        session["turns"].append(row)
    ordered: list[dict] = []
    for session in sessions.values():
        session["turns"].sort(key=lambda item: item["turn_number"])
        ordered.append(session)
    return ordered


def _build_turn_efficiency_plot(
    sessions: Sequence[dict], athlete_name: str, stroke: str
) -> bytes | None:
    """Plot average turn efficiency per session."""

    points = []
    for entry in sessions:
        turns = [
            row for row in entry["turns"] if row.get("total_turn_time") is not None
        ]
        if not turns:
            continue
        average = sum(row["total_turn_time"] for row in turns) / len(turns)
        points.append((entry["timestamp"], average))
    if not points:
        return None
    dates, values = zip(*sorted(points, key=lambda item: item[0]))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(dates, values, marker="o", linewidth=2)
    ax.set_title(
        f"Ефективність поворотів ({_stroke_title(stroke)}) – {athlete_name or 'спортсмен'}"
    )
    ax.set_xlabel("Дата тренування")
    ax.set_ylabel("Середній час повороту, с")
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.autofmt_xdate()
    return _figure_to_png(fig)


def _build_turn_comparison_plot(
    sessions: Sequence[dict], athlete_name: str, stroke: str
) -> bytes | None:
    """Plot comparison of turn times for the most recent session."""

    if not sessions:
        return None
    latest = max(sessions, key=lambda item: item["timestamp"])
    turns = [row for row in latest["turns"] if row.get("total_turn_time") is not None]
    if not turns:
        return None
    turns.sort(key=lambda row: row["turn_number"])
    labels = [f"#{row['turn_number']}" for row in turns]
    values = [row["total_turn_time"] for row in turns]
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(labels, values, color="#1f77b4")
    ax.set_title(
        f"Порівняння поворотів (останній заплив) – {athlete_name or 'спортсмен'}"
    )
    ax.set_xlabel("Номер повороту")
    ax.set_ylabel("Час, с")
    ax.bar_label(bars, fmt="{:.2f}")
    return _figure_to_png(fig)


def _build_turn_heatmap(
    sessions: Sequence[dict], athlete_name: str, stroke: str
) -> bytes | None:
    """Return heatmap visualising turn efficiency per session."""

    if not sessions:
        return None
    turn_numbers = sorted(
        {row["turn_number"] for item in sessions for row in item["turns"]}
    )
    if not turn_numbers:
        return None
    session_keys = sorted(sessions, key=lambda item: item["timestamp"])
    matrix: list[list[float | None]] = []
    for turn_number in turn_numbers:
        row_values: list[float | None] = []
        for session in session_keys:
            value = None
            for item in session["turns"]:
                if item["turn_number"] == turn_number:
                    value = item.get("total_turn_time")
                    break
            row_values.append(value)
        matrix.append(row_values)
    if not any(any(value is not None for value in row) for row in matrix):
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    clean_matrix = [
        [value if value is not None else 0.0 for value in row] for row in matrix
    ]
    im = ax.imshow(clean_matrix, aspect="auto", cmap="viridis")
    ax.set_title(
        f"Теплова карта поворотів ({_stroke_title(stroke)}) – {athlete_name or 'спортсмен'}"
    )
    ax.set_xlabel("Тренування")
    ax.set_ylabel("Номер повороту")
    ax.set_xticks(range(len(session_keys)))
    ax.set_xticklabels(
        [session["timestamp"].strftime("%d.%m") for session in session_keys],
        rotation=45,
    )
    ax.set_yticks(range(len(turn_numbers)))
    ax.set_yticklabels([str(num) for num in turn_numbers])
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Час, с")
    return _figure_to_png(fig)


def _format_turn_summary(stroke: str, progress: Sequence[TurnProgressResult]) -> str:
    """Return formatted summary highlighting best and worst turns."""

    if not progress:
        return (
            f"<b>Аналіз поворотів ({_stroke_title(stroke)})</b>\n"
            "Недостатньо даних для оцінки."
        )
    sorted_progress = sorted(
        progress, key=lambda item: item.improvement_rate, reverse=True
    )
    top = sorted_progress[:3]
    worst = sorted(progress, key=lambda item: item.improvement_rate)[:3]
    lines = [f"<b>Аналіз поворотів ({_stroke_title(stroke)})</b>"]
    lines.append("🔝 Топ-3 ефективних поворотів:")
    for item in top:
        lines.append(
            "• #{num}: {rate:+.1f}% (тренд {trend:+.3f} c)".format(
                num=item.turn_number,
                rate=item.improvement_rate,
                trend=item.efficiency_trend,
            )
        )
    lines.append("⚠️ Потребують уваги:")
    for item in worst:
        lines.append(
            "• #{num}: {rate:+.1f}% (тренд {trend:+.3f} c)".format(
                num=item.turn_number,
                rate=item.improvement_rate,
                trend=item.efficiency_trend,
            )
        )
    return "\n".join(lines)


async def _send_progress_report(
    event: types.Message | types.CallbackQuery,
    athlete_id: int,
    stats_service: StatsService,
) -> None:
    """Render progress for athlete and send to requester."""

    try:
        worksheet = get_results_worksheet()
        raw_rows = worksheet.get_all_values()
    except RuntimeError as exc:
        logger.error("Failed to access results worksheet: %s", exc, exc_info=True)
        target = event.message if isinstance(event, types.CallbackQuery) else event
        await target.answer("Не вдалося отримати доступ до таблиці результатів.")
        if isinstance(event, types.CallbackQuery):
            await event.answer()
        return
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

    try:
        image_bytes = _build_progress_plot(distances, athlete_name)
    except Exception as exc:  # pragma: no cover - plotting guard
        logger.error("Failed to build progress plot: %s", exc, exc_info=True)
        image_bytes = None
    table_text = _format_progress_table(distances)

    target = event.message if isinstance(event, types.CallbackQuery) else event
    if image_bytes is not None:
        await target.answer_photo(
            BufferedInputFile(image_bytes, filename=f"progress_{athlete_key}.png"),
            caption=f"📈 Прогрес для {athlete_name}",
        )
    else:
        await target.answer(
            "⚠️ Не вдалося побудувати графік прогресу. Нижче наведено таблицю з даними.",
        )
    await target.answer(
        "<b>Динаміка за дистанціями</b>\n" + table_text,
        parse_mode="HTML",
    )

    tasks = {
        stroke: asyncio.create_task(
            stats_service.get_turn_analytics(athlete_id, stroke)
        )
        for stroke in _SUPPORTED_TURN_STROKES
    }
    turn_sections: list[str] = []
    for stroke, task in tasks.items():
        try:
            analytics = await task
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to load turn analytics for %s: %s", stroke, exc)
            continue
        progress = analytics.get("progress", ())
        if not progress:
            continue
        turn_sections.append(_format_turn_summary(stroke, progress))
    if turn_sections:
        await target.answer("\n\n".join(turn_sections), parse_mode="HTML")
    if isinstance(event, types.CallbackQuery):
        await event.answer()


@router.message(Command("progress"))
async def cmd_progress(
    message: types.Message, role_service: RoleService, stats_service: StatsService
) -> None:
    """Ask to choose athlete for progress visualization."""

    await role_service.upsert_user(message.from_user)
    role = await role_service.get_role(message.from_user.id)
    if role == ROLE_ATHLETE:
        await _send_progress_report(message, message.from_user.id, stats_service)
        return

    try:
        worksheet = get_athletes_worksheet()
        records = worksheet.get_all_records()
    except RuntimeError as exc:
        logger.error("Failed to access athletes worksheet: %s", exc, exc_info=True)
        await message.answer(
            "Не вдалося отримати доступ до таблиці спортсменів. Спробуйте пізніше."
        )
        return
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
async def show_progress(
    cb: types.CallbackQuery, role_service: RoleService, stats_service: StatsService
) -> None:
    """Generate progress visualization for selected athlete."""

    try:
        athlete_id = int(cb.data.split("_", 2)[-1])
    except ValueError:
        await cb.answer("Некоректний ідентифікатор.", show_alert=True)
        return

    if not await role_service.can_access_athlete(cb.from_user.id, athlete_id):
        await cb.answer("Немає доступу до цього спортсмена.", show_alert=True)
        return

    await _send_progress_report(cb, athlete_id, stats_service)


def _parse_turn_command(message: types.Message) -> tuple[str | None, int | None]:
    """Parse stroke and optional athlete id from the command."""

    text = (message.text or "").strip()
    parts = text.split()
    stroke = None
    athlete_id = None
    if len(parts) >= 2:
        stroke = _normalize_stroke(parts[1])
    if len(parts) >= 3:
        try:
            athlete_id = int(parts[2])
        except ValueError:
            athlete_id = None
    return stroke, athlete_id


@router.message(Command("turn_analysis"))
async def cmd_turn_analysis(
    message: types.Message,
    stats_service: StatsService,
    role_service: RoleService,
) -> None:
    """Provide detailed turn analytics with visualisations."""

    user = message.from_user
    if user is None:
        await message.answer("Команда доступна лише для зареєстрованих користувачів.")
        return
    stroke_arg, requested_id = _parse_turn_command(message)
    stroke = stroke_arg or _DEFAULT_TURN_STROKE
    if stroke not in _SUPPORTED_TURN_STROKES:
        await message.answer(
            "Доступні стилі: breaststroke, butterfly. Приклад: /turn_analysis butterfly"
        )
        return

    role = await role_service.get_role(user.id)
    if role == ROLE_ATHLETE:
        athlete_id = user.id
    else:
        if requested_id is None:
            await message.answer(
                "Вкажіть ID спортсмена: /turn_analysis butterfly 123456"
            )
            return
        athlete_id = requested_id
        if not await role_service.can_access_athlete(user.id, athlete_id):
            await message.answer("Немає доступу до цього спортсмена.")
            return

    status_msg = await message.answer("Готую аналітику поворотів…")
    try:
        analytics = await stats_service.get_turn_analytics(athlete_id, stroke)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error("Failed to load turn analytics: %s", exc, exc_info=True)
        await status_msg.edit_text("Не вдалося отримати дані аналізу поворотів.")
        return
    rows = analytics.get("rows", ())
    if not rows:
        await status_msg.edit_text("Поки немає поворотів для аналізу цього стилю.")
        return

    sessions = _group_turn_sessions(rows)
    athlete_name = rows[0].get("athlete_name") if rows else ""

    plots = [
        (
            _build_turn_efficiency_plot,
            "turn_efficiency.png",
            "Середній час повороту за тренуваннями",
        ),
        (
            _build_turn_comparison_plot,
            "turn_comparison.png",
            "Порівняння поворотів в останньому запливі",
        ),
        (
            _build_turn_heatmap,
            "turn_heatmap.png",
            "Теплова карта ефективності",
        ),
    ]
    await status_msg.edit_text("Аналітика готова. Надсилаю графіки…")
    for builder, filename, caption in plots:
        try:
            image = builder(sessions, athlete_name, stroke)
        except Exception as exc:  # pragma: no cover - plotting guard
            logger.warning("Failed to render %s: %s", filename, exc, exc_info=True)
            await message.answer(
                f"⚠️ Не вдалося побудувати графік: {caption}. Спробуйте пізніше."
            )
            continue
        if not image:
            continue
        await message.answer_photo(
            BufferedInputFile(image, filename=filename),
            caption=caption,
        )

    summary = analytics.get("progress", ())
    if summary:
        await message.answer(
            _format_turn_summary(stroke, summary),
            parse_mode="HTML",
        )
    try:
        comparison = await stats_service.compare_turn_efficiency(
            athlete_id, StatsPeriod.WEEK
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.warning("Failed to compute turn comparison: %s", exc)
        return
    comparisons = comparison.get("comparisons", ())
    if comparisons:
        lines = ["<b>Порівняння із попереднім тижнем</b>"]
        for item in comparisons:
            if item.delta is None:
                continue
            percent = item.percent_change
            lines.append(
                "• Поворот #{num}: {delta:+.2f} c ({percent:+.1f}%)".format(
                    num=item.turn_number,
                    delta=item.delta,
                    percent=percent if percent is not None else 0.0,
                )
            )
        if len(lines) > 1:
            await message.answer("\n".join(lines), parse_mode="HTML")
