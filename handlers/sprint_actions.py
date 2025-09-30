"""Sprint-related handlers and UI helpers.

Приклад взаємодії користувача:

1. Натискає «Додати результат ➕» → бот показує кнопки дистанцій.
2. Обирає «🔥 100 м кроль» із шаблонів → бот одразу просить час першого відрізку.
3. Вводить проміжні результати у форматі ``0:32.45`` → бот підказує наступні відрізки.
4. Отримує підсумок з аналізом та кнопку «🔁 Повторити попередній результат».
5. Натискає «🔁» → бот дублює результат з новим часом та аналізом.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from keyboards import (
    DistanceCB,
    RepeatCB,
    StrokeCB,
    TemplateCB,
    get_distance_keyboard,
    get_repeat_keyboard,
    get_stroke_keyboard,
    get_template_keyboard,
)
from services import ADMIN_IDS, ws_athletes, ws_log, ws_pr, ws_results
from utils import AddResult, fmt_time, get_segments, parse_time, pr_key, speed

router = Router()


@dataclass(frozen=True)
class SprintTemplate:
    """Describe reusable sprint presets."""

    template_id: str
    title: str
    dist: int
    stroke: str
    hint: str


SPRINT_TEMPLATES: tuple[SprintTemplate, ...] = (
    SprintTemplate(
        template_id="50_free",
        title="⚡️ 50 м кроль",
        dist=50,
        stroke="freestyle",
        hint="4×12.5 м — вибуховий старт та потужний фініш.",
    ),
    SprintTemplate(
        template_id="100_free",
        title="🔥 100 м кроль",
        dist=100,
        stroke="freestyle",
        hint="4×25 м. Другий відрізок контрольний, третій — прискорення.",
    ),
    SprintTemplate(
        template_id="100_fly",
        title="🦋 100 м батерфляй",
        dist=100,
        stroke="butterfly",
        hint="4×25 м. Тримайте стабільну техніку й темп.",
    ),
    SprintTemplate(
        template_id="200_mixed",
        title="🥇 200 м комплекс",
        dist=200,
        stroke="medley",
        hint="По 50 м на стиль: батерфляй, спина, брас, кроль.",
    ),
)

TEMPLATE_MAP = {template.template_id: template for template in SPRINT_TEMPLATES}

# (coach_id, athlete_id) -> stored data for quick repeat
LAST_RESULTS: dict[tuple[int, int], dict[str, Any]] = {}


def _segment_prompt(idx: int, length: float) -> str:
    """Return formatted prompt for segment input."""

    distance = f"{length:g}"
    return (
        f"Час відрізку #{idx + 1} ({distance} м).\n"
        "Формат відповіді: 0:32.45 або 32.45"
    )


def _persist_result(
    athlete_id: int,
    athlete_name: str,
    stroke: str,
    dist: int,
    splits: Iterable[float],
) -> tuple[float, list[tuple[int, float]], str]:
    """Save result to Google Sheets and return totals."""

    splits_list = list(splits)
    total = sum(splits_list)
    timestamp = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")

    ws_results.append_row(
        [
            athlete_id,
            athlete_name,
            stroke,
            dist,
            timestamp,
            json.dumps(splits_list),
            total,
        ]
    )
    ws_log.append_row([athlete_id, timestamp, "ADD", json.dumps(splits_list)])

    new_prs: list[tuple[int, float]] = []
    for idx, seg_time in enumerate(splits_list):
        key = pr_key(athlete_id, stroke, dist, idx)
        cell = ws_pr.find(key)
        if not cell:
            ws_pr.append_row([key, seg_time, timestamp])
            new_prs.append((idx, seg_time))
            continue

        old = float(ws_pr.cell(cell.row, 2).value.replace(",", "."))
        if seg_time < old:
            ws_pr.update(f"A{cell.row}:C{cell.row}", [[key, seg_time, timestamp]])
            new_prs.append((idx, seg_time))

    return total, new_prs, timestamp


def _analysis_text(dist: int, splits: list[float], total: float) -> str:
    """Compose analysis block for the result."""

    seg_lens = get_segments(dist)
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


@router.callback_query(F.data == "add")
async def add(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Start collecting sprint result."""

    await cb.message.answer(
        "Оберіть дистанцію або введіть вручну:",
        reply_markup=get_distance_keyboard(),
    )
    await state.set_state(AddResult.choose_dist)


@router.callback_query(DistanceCB.filter(), AddResult.choose_dist)
async def distance_selected(
    cb: types.CallbackQuery, callback_data: DistanceCB, state: FSMContext
) -> None:
    """Handle distance choice from keyboard."""

    await cb.answer()
    dist = callback_data.value
    await state.update_data(dist=dist, splits=[], idx=0)
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
async def choose_template(cb: types.CallbackQuery) -> None:
    """Show list of sprint templates."""

    await cb.answer()
    template_pairs = ((tpl.template_id, tpl.title) for tpl in SPRINT_TEMPLATES)
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
    cb: types.CallbackQuery, callback_data: TemplateCB, state: FSMContext
) -> None:
    """Handle template selection and jump straight to time collection."""

    template = TEMPLATE_MAP.get(callback_data.template_id)
    if not template:
        await cb.answer("Шаблон не знайдено", show_alert=True)
        return

    await cb.answer()
    segs = get_segments(template.dist)
    await state.update_data(
        dist=template.dist,
        splits=[],
        idx=0,
        stroke=template.stroke,
        template_id=template.template_id,
    )
    await state.set_state(AddResult.collect)
    hint = f"💡 {template.hint}" if template.hint else ""
    await cb.message.answer(
        "✅ Обрано шаблон «{title}».\n{hint}\n{prompt}".format(
            title=template.title,
            hint=hint,
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
    await state.update_data(dist=dist, splits=[], idx=0)
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
    segs = get_segments(dist)
    await cb.message.answer(_segment_prompt(0, segs[0]))
    await state.set_state(AddResult.collect)


@router.message(AddResult.collect)
async def collect(message: types.Message, state: FSMContext) -> None:
    """Collect segment times and save result."""

    data = await state.get_data()
    athlete_id = data.get("athlete_id", message.from_user.id)
    dist, idx, splits = data["dist"], data["idx"], data["splits"]
    segs = get_segments(dist)
    try:
        t = parse_time(message.text)
    except Exception:
        return await message.reply("❗ Невірний формат. Приклади: 0:32.45 або 32.45")
    splits.append(t)
    if idx + 1 < len(segs):
        await state.update_data(idx=idx + 1, splits=splits)
        await message.answer(_segment_prompt(idx + 1, segs[idx + 1]))
        return
    await state.clear()
    stroke = data.get("stroke", "freestyle")
    try:
        total, new_prs, _ = _persist_result(
            athlete_id,
            message.from_user.full_name,
            stroke,
            dist,
            splits,
        )
    except Exception as exc:
        logging.error("Failed to save result to Google Sheets: %s", exc, exc_info=True)
        return await message.answer(
            "Помилка при збереженні результату. Спробуйте пізніше."
        )
    txt = (
        f"✅ Збережено! Загальий час <b>{fmt_time(total)}</b>\n"
        f"Середня швидкість {speed(dist, total):.2f} м/с"
    )
    if new_prs:
        txt += "\n" + "\n".join(
            f"🥳 Новий PR сегменту #{i+1}: {fmt_time(t)}" for i, t in new_prs
        )
    await message.answer(
        txt,
        parse_mode="HTML",
        reply_markup=get_repeat_keyboard(athlete_id),
    )

    analysis_text = _analysis_text(dist, splits, total)
    await message.answer(analysis_text, parse_mode="HTML")

    LAST_RESULTS[(message.from_user.id, athlete_id)] = {
        "athlete_id": athlete_id,
        "athlete_name": message.from_user.full_name,
        "stroke": stroke,
        "dist": dist,
        "splits": list(splits),
    }


@router.callback_query(RepeatCB.filter())
async def repeat_previous(cb: types.CallbackQuery, callback_data: RepeatCB) -> None:
    """Duplicate the previously saved result for faster logging."""

    key = (cb.from_user.id, callback_data.athlete_id)
    payload = LAST_RESULTS.get(key)
    if not payload:
        await cb.answer("Немає результату для повтору", show_alert=True)
        return

    await cb.answer()
    try:
        total, new_prs, _ = _persist_result(
            payload["athlete_id"],
            payload["athlete_name"],
            payload["stroke"],
            payload["dist"],
            payload["splits"],
        )
    except Exception as exc:
        logging.error("Failed to repeat result: %s", exc, exc_info=True)
        await cb.message.answer(
            "Не вдалося повторити попередній результат. Спробуйте пізніше."
        )
        return

    dist = payload["dist"]
    txt = (
        "🔁 Продубльовано попередній результат!\n"
        f"Загальний час <b>{fmt_time(total)}</b>\n"
        f"Середня швидкість {speed(dist, total):.2f} м/с"
    )
    if new_prs:
        txt += "\n" + "\n".join(
            f"🥳 Новий PR сегменту #{i+1}: {fmt_time(t)}" for i, t in new_prs
        )

    await cb.message.answer(
        txt,
        parse_mode="HTML",
        reply_markup=get_repeat_keyboard(payload["athlete_id"]),
    )

    analysis_text = _analysis_text(dist, payload["splits"], total)
    await cb.message.answer(analysis_text, parse_mode="HTML")


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


@router.callback_query(F.data == "admin")
async def admin(cb: types.CallbackQuery) -> None:
    """Admin placeholder."""

    if str(cb.from_user.id) not in ADMIN_IDS:
        return
    await cb.message.answer("Адмін‑панель у процесі. Дані видно в Google Sheets.")


@router.callback_query(F.data == "menu_sprint")
async def menu_sprint(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Show list of athletes for result entry."""

    try:
        records = ws_athletes.get_all_records()
    except Exception as e:
        logging.error(f"Failed to get athletes list: {e}")
        return await cb.message.answer(
            "Помилка: не вдалося отримати список спортсменів. Спробуйте пізніше."
        )

    buttons = []
    for rec in records:
        athlete_id = rec["ID"]
        athlete_name = rec.get("Name", str(athlete_id))
        buttons.append(
            InlineKeyboardButton(
                text=athlete_name, callback_data=f"select_{athlete_id}"
            )
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[buttons])
    await cb.message.answer("Оберіть спортсмена:", reply_markup=kb)
    await state.set_state(AddResult.choose_athlete)


@router.callback_query(F.data.startswith("select_"))
async def select_athlete(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Save selected athlete and ask for distance."""

    try:
        athlete_id = int(cb.data.split("_", 1)[1])
    except ValueError:
        return await cb.message.answer("Помилка: ID спортсмена має бути числом.")
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


@router.callback_query(F.data == "menu_admin")
async def alias_admin(cb: types.CallbackQuery) -> None:
    """Menu alias for admin panel."""

    await admin(cb)


@router.callback_query(F.data == "menu_stayer")
async def menu_stayer(cb: types.CallbackQuery) -> None:
    """Notify that stayer block is under construction."""

    await cb.message.answer("🚧 Блок «Стаєр» ще в розробці – скоро буде!")
