import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
import asyncio
import math

# ───────────────────────── CONFIG ──────────────────────────
API_TOKEN = os.getenv("SPRINT_BOT_TOKEN", "YOUR_TOKEN_HERE")  # ⚠️ set env var!
ADMIN_IDS = {597164575}  # Telegram IDs with admin rights
CREDENTIALS_FILE = "creds.json"
SPREADSHEET_NAME = "SprintBotData"

# ───────────────────── GOOGLE SHEETS SETUP ─────────────────
if not os.path.exists(CREDENTIALS_FILE):
    raise SystemExit(f"⛔ Creds file {CREDENTIALS_FILE} not found. Place it next to the script.")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
client = gspread.authorize(creds)

try:
    book = client.open(SPREADSHEET_NAME)
except gspread.SpreadsheetNotFound:
    # Create and add worksheets if first launch
    book = client.create(SPREADSHEET_NAME)
    book.add_worksheet("ATHLETES", rows="1000", cols="10")
    book.add_worksheet("PR", rows="1000", cols="10")
    book.add_worksheet("LOG", rows="1000", cols="10")

ws_results = book.worksheet("ATHLETES")
ws_pr = book.worksheet("PR")
ws_log = book.worksheet("LOG")

# ────────────────────── AIROGRAM SETUP ─────────────────────
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

# ──────────────────────── UTILITIES ────────────────────────

def parse_time(inp: str) -> float:
    """Return seconds float from formats 1:05.73 or 32.5 etc."""
    inp = inp.strip().replace(",", ".")
    if ":" in inp:
        minute, sec = inp.split(":", 1)
        return int(minute) * 60 + float(sec)
    return float(inp)

def fmt_time(sec: float) -> str:
    m, s = divmod(sec, 60)
    return f"{int(m)}:{s:05.2f}" if m else f"{s:0.2f}"

def speed(distance: float, time_sec: float) -> float:
    return distance / time_sec if time_sec else 0

# Build segment blueprint for freestyle distances 50‑400+

def get_segments(distance: int):
    if distance == 50:
        return [12.5, 12.5, 0, 12.5, 12.5]  # 0 value = turn placeholder
    if distance == 100:
        return [25, 25, 25, 25]
    if distance == 200:
        return [50, 50, 50, 50]
    if distance >= 400:
        segs = [50] + [100] * ((distance - 50) // 100)
        leftover = distance - sum(segs)
        if leftover:
            segs.append(leftover)
        return segs
    raise ValueError("Unsupported distance")

# Keys to identify PR rows (ID|Stroke|Dist|SegIdx)

def pr_key(user_id: int, stroke: str, distance: int, seg_idx: int):
    return f"{user_id}|{stroke}|{distance}|{seg_idx}"

# ─────────────── FSM for adding result interaction ─────────
class AddResult(StatesGroup):
    selecting_dist = State()
    collecting_splits = State()


# ─────────────────────── BOT HANDLERS ──────────────────────
@dp.message(Command("start"))
async def start(msg: types.Message):
    kb = [
        [InlineKeyboardButton("➕ Додати результат", callback_data="add")],
        [InlineKeyboardButton("📜 Моя історія", callback_data="history")],
        [InlineKeyboardButton("🏆 Мої рекорди", callback_data="records")],
    ]
    if msg.from_user.id in ADMIN_IDS:
        kb.append([InlineKeyboardButton("🛠 Admin", callback_data="admin")])

    await msg.answer("Привіт, атлете! Обери дію:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# ------- ADD RESULT FLOW -------
@dp.callback_query(F.data == "add")
async def add_begin(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("Введи дистанцію (50/100/200/400/800/1500):")
    await state.set_state(AddResult.selecting_dist)

@dp.message(AddResult.selecting_dist)
async def add_distance(msg: types.Message, state: FSMContext):
    try:
        dist = int(msg.text)
        if dist not in {50, 100, 200, 400, 800, 1500}:
            raise ValueError
    except ValueError:
        return await msg.reply("❗ Невірна дистанція. Спробуй ще.")
    await state.update_data(distance=dist, splits=[], idx=0)
    segs = get_segments(dist)
    await msg.answer(f"Дистанція {dist} м. Введи час для сегмента №1 ({segs[0]} м):")
    await state.set_state(AddResult.collecting_splits)

@dp.message(AddResult.collecting_splits)
async def collect_splits(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    dist = data["distance"]
    segs = get_segments(dist)
    idx = data["idx"]
    try:
        t = parse_time(msg.text)
    except Exception:
        return await msg.reply("❗ Неправильний формат часу. Приклад 0:32.45 або 32.45")
    splits = data["splits"] + [t]
    if idx + 1 < len(segs):
        await state.update_data(splits=splits, idx=idx + 1)
        await msg.answer(f"Час сегмента №{idx+2} ({segs[idx+1]} м):")
        return
    # All splits collected – store
    await state.clear()
    total_time = sum(splits)
    stroke = "freestyle"  # current version supports only freestyle end‑to‑end
    now_iso = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    record_row = [msg.from_user.id, msg.from_user.full_name or "Athlete", stroke, dist, now_iso,
                  json.dumps(splits), total_time]
    ws_results.append_row(record_row)

    # PR detection per segment
    new_records = []
    for i, seg_time in enumerate(splits):
        key = pr_key(msg.from_user.id, stroke, dist, i)
        pr_cells = ws_pr.findall(key)
        if not pr_cells:
            # no PR yet – create
            ws_pr.append_row([key, seg_time, now_iso])
            new_records.append((i, seg_time))
        else:
            row_idx = pr_cells[0].row
            prev_time = float(ws_pr.cell(row_idx, 2).value)
            if seg_time < prev_time:
                ws_pr.update_row(row_idx, [key, seg_time, now_iso])
                new_records.append((i, seg_time))
    # Send confirmations
    txt = f"✅ Результат збережено!\nЗагальний час: <b>{fmt_time(total_time)}</b> (середня швидкість {speed(dist,total_time):.2f} м/с)"
    if new_records:
        pr_lines = [f"🥳 Новий рекорд сегменту #{i+1}: {fmt_time(t)}" for i, t in new_records]
        txt += "\n" + "\n".join(pr_lines)
    await msg.answer(txt)
    # Log
    ws_log.append_row([msg.from_user.id, now_iso, "ADD_RESULT", json.dumps(record_row)])

# ------- HISTORY -------
@dp.callback_query(F.data == "history")
async def history(cb: CallbackQuery):
    rows = ws_results.get_all_values()
    out = []
    for row in rows[::-1]:  # newest first
        if str(row[0]) == str(cb.from_user.id):
            dist = row[3]
            splits = json.loads(row[5])
            for i, t in enumerate(splits):
                s_speed = speed(get_segments(int(dist))[i], t)
                out.append(f"{row[4]} | {dist} м seg#{i+1}: {fmt_time(float(t))} ({s_speed:.2f} м/с)")
            if len(out) > 30:
                break
    await cb.message.answer("\n".join(out) if out else "Поки історія пуста.")

# ------- RECORDS / BESTS -------
@dp.callback_query(F.data == "records")
async def records(cb: CallbackQuery):
    user = cb.from_user.id
    pr_rows = ws_pr.get_all_values()
    best_dict = {}
    for row in pr_rows:
        uid, stroke, dist, seg_idx = row[0].split("|")
        if int(uid) != user:
            continue
        best_dict.setdefault(dist, []).append(float(row[1]))
    if not best_dict:
        return await cb.message.answer("Поки рекордів нема – додай результати 🤿")
    lines = []
    for dist, seg_times in best_dict.items():
        total = sum(seg_times)
        seg_str = " • ".join(fmt_time(t) for t in seg_times)
        lines.append(f"🏅 {dist} м → {fmt_time(total)} (сумма кращих)\n{seg_str}")
    await cb.message.answer("\n\n".join(lines))

# ------- ADMIN PANEL -------
@dp.callback_query(F.data == "admin")
async def admin(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return
    await cb.message.answer("<i>Адмінка ще у розробці – експортувати CSV / видаляти рядки можна у Google Sheets напряму.</i>")

# ─────────────────────── MAIN APP ─────────────────────────
async def main():
    print("[SprintBot] starting…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
