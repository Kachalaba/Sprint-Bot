from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from keyboards import StrokeCB, get_stroke_keyboard, get_history_keyboard
from services.google_sheets import ADMIN_IDS, ws_athletes, ws_log, ws_pr, ws_results
from utils import AddResult, fmt_time, get_segments, parse_time, pr_key, speed

router = Router()


@router.callback_query(F.data == "add")
async def add(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Start collecting sprint result."""
    await cb.message.answer("Введіть дистанцію (50/100/200/400/800/1500):")
    await state.set_state(AddResult.choose_dist)


@router.message(AddResult.choose_dist)
async def dist_chosen(message: types.Message, state: FSMContext) -> None:
    """Handle chosen distance."""
    try:
        dist = int(message.text)
        if dist not in {50, 100, 200, 400, 800, 1500}:
            raise ValueError
    except ValueError:
        return await message.reply("❗ Неправильна дистанція. Спробуйте ще.")
    await state.update_data(dist=dist, splits=[], idx=0)
    await message.answer("Оберіть стиль плавання:", reply_markup=get_stroke_keyboard())
    await state.set_state(AddResult.waiting_for_stroke)


@router.callback_query(StrokeCB.filter())
async def stroke_chosen(
    cb: types.CallbackQuery, callback_data: StrokeCB, state: FSMContext
) -> None:
    """Save stroke and ask for first split."""
    await state.update_data(stroke=callback_data.stroke)
    data = await state.get_data()
    dist = data["dist"]
    segs = get_segments(dist)
    await cb.message.answer(f"Дистанція {dist} м. Час відрізку #1 ({segs[0]} м):")
    await state.set_state(AddResult.collect)


@router.message(AddResult.collect)
async def collect(message: types.Message, state: FSMContext) -> None:
    """Collect segment times and save result."""
    data = await state.get_data()
    athlete_id = data.get("athlete_id")
    dist, idx, splits = data["dist"], data["idx"], data["splits"]
    segs = get_segments(dist)
    try:
        t = parse_time(message.text)
    except Exception:
        return await message.reply("❗ Формат 0:32.45 або 32.45")
    splits.append(t)
    if idx + 1 < len(segs):
        await state.update_data(idx=idx + 1, splits=splits)
        await message.answer(f"Час відрізку #{idx + 2} ({segs[idx + 1]} м):")
        return
    await state.clear()
    total = sum(splits)
    stroke = data.get("stroke", "freestyle")
    now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
    try:
        ws_results.append_row(
            [
                athlete_id,
                message.from_user.full_name,
                stroke,
                dist,
                now,
                json.dumps(splits),
                total,
            ]
        )
        ws_log.append_row([athlete_id, now, "ADD", json.dumps(splits)])
    except Exception:
        return await message.answer(
            "Помилка при збереженні результату. Спробуйте пізніше."
        )
    new_prs = []
    for i, seg_time in enumerate(splits):
        key = pr_key(message.from_user.id, stroke, dist, i)
        cell = ws_pr.find(key) if ws_pr.findall(key) else None
        if not cell:
            ws_pr.append_row([key, seg_time, now])
            new_prs.append((i, seg_time))
        else:
            old = float(ws_pr.cell(cell.row, 2).value.replace(",", "."))
            if seg_time < old:
                # --- ИСПРАВЛЕННАЯ СТРОКА ---
                ws_pr.update(f'A{cell.row}:C{cell.row}', [[key, seg_time, now]])
                new_prs.append((i, seg_time))
    txt = (
        f"✅ Збережено! Загальний час <b>{fmt_time(total)}</b>\n"
        f"Середня швидкість {speed(dist, total):.2f} м/с"
    )
    if new_prs:
        txt += "\n" + "\n".join(
            f"🥳 Новий PR сегменту #{i+1}: {fmt_time(t)}" for i, t in new_prs
        )
    await message.answer(txt, parse_mode="HTML")
    seg_lens = get_segments(dist)
    speeds = [speed(seg, t) for seg, t in zip(seg_lens, splits)]
    avg_speed = speed(dist, total)
    pace = total / dist * 100
    degradation = (
        (speeds[0] - speeds[-1]) / speeds[0] * 100 if speeds and speeds[0] else 0
    )
    analysis_text = (
        "📊 <b>Аналіз результату</b>\n"
        f"• Швидкості по сегментах: "
        + " • ".join(f"{v:.2f} м/с" for v in speeds)
        + "\n"
        f"• Середня швидкість: {avg_speed:.2f} м/с\n"
        f"• Темп: {pace:.1f} сек/100 м\n"
        f"• Деградація темпу: {degradation:.1f}%"
    )
    await message.answer(analysis_text, parse_mode="HTML")


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
                    logging.warning(f"Skipping malformed row for user {cb.from_user.id}: {row}. Error: {e}")
                    continue

                if processed_count >= 10:
                    out.append("...")
                    break
                    
        await cb.message.answer("\n".join(out) if out else "Історія поки порожня.", parse_mode="HTML")
    
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
                best.setdefault(dist, []).append(float(row[1].replace(",", ".")))
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
    if cb.from_user.id not in ADMIN_IDS:
        return
    await cb.message.answer("Адмін‑панель у процесі. Дані видно в Google Sheets.")


@router.callback_query(F.data == "menu_sprint")
async def menu_sprint(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Show list of athletes for result entry."""
    try:
        records = ws_athletes.get_all_records()
    except Exception:
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
    await cb.message.answer("Введіть дистанцію (50/100/200/400/800/1500):")
    await state.set_state(AddResult.choose_dist)


@router.callback_query(F.data == "menu_history")
async def menu_history(cb: types.CallbackQuery) -> None:
    """Menu alias for history."""
    await history(cb)


@router.callback__query(F.data == "menu_records")
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
