from __future__ import annotations

import json
from datetime import datetime, timezone

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services import ADMIN_IDS, ws_athletes, ws_log, ws_pr, ws_results
from utils import AddResult, fmt_time, get_segments, parse_time, pr_key, speed

router = Router()


@router.callback_query(F.data == "add")
async def add(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Start collecting sprint result."""
    await cb.message.answer("Введи дистанцію (50/100/200/400/800/1500):")
    await state.set_state(AddResult.choose_dist)


@router.message(AddResult.choose_dist)
async def dist_chosen(message: types.Message, state: FSMContext) -> None:
    """Handle chosen distance."""
    try:
        dist = int(message.text)
        if dist not in {50, 100, 200, 400, 800, 1500}:
            raise ValueError
    except ValueError:
        return await message.reply("❗ Невірна дистанція. Спробуй ще.")
    await state.update_data(dist=dist, splits=[], idx=0)
    segs = get_segments(dist)
    await message.answer(f"Дистанція {dist} м. Час сегмента #1 ({segs[0]} м):")
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
        await message.answer(f"Час сегмента #{idx + 2} ({segs[idx + 1]} м):")
        return
    await state.clear()
    total = sum(splits)
    stroke = "freestyle"
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
            "Ошибка при сохранении результата. Попробуйте позже."
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
                ws_pr.update_row(cell.row, [key, seg_time, now])
                new_prs.append((i, seg_time))
    txt = (
        f"✅ Збережено! Загальний час <b>{fmt_time(total)}</b>\n"
        f"Середня швидкість {speed(dist, total):.2f} м/с"
    )
    if new_prs:
        txt += "\n" + "\n".join(
            f"🥳 Новий PR сег #{i+1}: {fmt_time(t)}" for i, t in new_prs
        )
    await message.answer(txt)
    seg_lens = get_segments(dist)
    speeds = [speed(seg, t) for seg, t in zip(seg_lens, splits)]
    avg_speed = speed(dist, total)
    pace = total / dist * 100
    degradation = (
        (speeds[0] - speeds[-1]) / speeds[0] * 100 if speeds and speeds[0] else 0
    )
    analysis_text = (
        "📊 <b>Аналіз результату</b>\n"
        f"• Швидкості по сегментам: "
        + " • ".join(f"{v:.2f} м/с" for v in speeds)
        + "\n"
        f"• Середня швидкість: {avg_speed:.2f} м/с\n"
        f"• Темп: {pace:.1f} сек/100 м\n"
        f"• Деградація темпу: {degradation:.1f}%"
    )
    await message.answer(analysis_text)


@router.callback_query(F.data == "history")
async def history(cb: types.CallbackQuery) -> None:
    """Show history of results for user."""
    rows = ws_results.get_all_values()[::-1]
    out = []
    for row in rows:
        if row and str(row[0]) == str(cb.from_user.id):
            dist = int(row[3])
            splits = json.loads(row[5])
            date = row[4]
            for i, t in enumerate(splits):
                out.append(
                    f"{date} | {dist} м seg#{i+1}: {fmt_time(float(t))} ("
                    f"{speed(get_segments(dist)[i], float(t)):.2f} м/с)"
                )
            if len(out) >= 30:
                break
    await cb.message.answer("\n".join(out) if out else "Поки історія пуста.")


@router.callback_query(F.data == "records")
async def records(cb: types.CallbackQuery) -> None:
    """Display personal records."""
    rows = ws_pr.get_all_values()
    best = {}
    for row in rows:
        uid, _, dist, _ = row[0].split("|")
        if int(uid) == cb.from_user.id:
            best.setdefault(dist, []).append(float(row[1].replace(",", ".")))
    if not best:
        return await cb.message.answer("Ще нема рекордів.")
    lines = []
    for dist, arr in best.items():
        total = sum(arr)
        lines.append(
            f"🏅 {dist} м → {fmt_time(total)} (сума кращих)\n"
            + " • ".join(fmt_time(t) for t in arr)
        )
    await cb.message.answer("\n\n".join(lines))


@router.callback_query(F.data == "admin")
async def admin(cb: types.CallbackQuery) -> None:
    """Admin placeholder."""
    if cb.from_user.id not in ADMIN_IDS:
        return
    await cb.message.answer("Адмін‑панель у процесі. Дані видно у Google Sheets.")


@router.callback_query(F.data == "menu_sprint")
async def menu_sprint(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Show list of athletes for result entry."""
    try:
        records = ws_athletes.get_all_records()
    except Exception:
        return await cb.message.answer(
            "Ошибка: не удалось получить список спортсменов. Попробуйте позже."
        )
    kb = InlineKeyboardMarkup(row_width=2)
    for rec in records:
        athlete_id = rec["ID"]
        athlete_name = rec.get("Name", str(athlete_id))
        kb.insert(
            InlineKeyboardButton(
                text=athlete_name, callback_data=f"select_{athlete_id}"
            )
        )
    await cb.message.answer("Выберите спортсмена:", reply_markup=kb)
    await state.set_state(AddResult.choose_athlete)


@router.callback_query(F.data.startswith("select_"))
async def select_athlete(cb: types.CallbackQuery, state: FSMContext) -> None:
    """Save selected athlete and ask for distance."""
    try:
        athlete_id = int(cb.data.split("_", 1)[1])
    except ValueError:
        return await cb.message.answer("Ошибка: ID спортсмена должен быть числом.")
    await state.update_data(athlete_id=athlete_id)
    await cb.message.answer("Введите дистанцию (50/100/200/400/800/1500):")
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
    await cb.message.answer("🚧 Блок «Стаер» ещё в разработке – скоро будет!")
