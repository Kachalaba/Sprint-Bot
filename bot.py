import os, json, math, asyncio
from datetime import datetime, timezone
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


# ───────────────────────── CONFIG ──────────────────────────
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise SystemExit("⛔ Переменная BOT_TOKEN не задана. См. .env.example")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "597164575").split(',') if x}
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "creds.json")  # JSON‑ключ сервис‑аккаунта
SPREADSHEET_KEY = os.getenv("SPREADSHEET_KEY", "1NA-BcyS4QQjMdnDi-jxM91qDIvwj43Z50bsjRph2UtU")

# ───────────────────── GOOGLE SHEETS ───────────────────────
if not os.path.exists(CREDENTIALS_FILE):
    raise SystemExit(f"⛔ Не найден {CREDENTIALS_FILE}. Помести JSON рядом с bot.py")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
try:
    book = client.open_by_key(SPREADSHEET_KEY)
except Exception:
    raise SystemExit("⛔ Таблица с таким ключом не найдена или нет доступа. Проверь Share.")
sheet_titles = {ws.title for ws in book.worksheets()}
for title in ("ATHLETES", "PR", "LOG"):
    if title not in sheet_titles:
        book.add_worksheet(title, rows="1000", cols="10")
ws_results = book.worksheet("ATHLETES")
ws_pr = book.worksheet("PR")
ws_log = book.worksheet("LOG")
# ───────────────────── REGISTRATION SHEET ───────────────────
# Создаём лист AthletesList, если его ещё нет
if "AthletesList" not in sheet_titles:
    book.add_worksheet("AthletesList", rows="1000", cols="3")
# Получаем объект листа для регистрации новых спортсменов
ws_athletes = book.worksheet("AthletesList")


# ────────────────────── AIROGRAM SETUP ─────────────────────
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
# ─────────────────── UI: Reply‑клавиатура ───────────────────
start_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Старт")],
        [KeyboardButton(text="Регистрация")]
    ],
    resize_keyboard=True
)

# ───────────────────────── HANDLERS ─────────────────────────
@dp.message(Command("reg"))
@dp.message(lambda m: m.text == "Регистрация")
async def cmd_reg(message: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Перешлите контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Перешлите контакт спортсмена:", reply_markup=kb)

@dp.message(lambda m: m.contact is not None)
async def reg_contact(message: types.Message):
    contact = message.contact
    ws_athletes.append_row([
        contact.user_id,
        contact.first_name or "",
        datetime.now(timezone.utc).isoformat(" ", "seconds")
    ])
    await message.answer(
        f"✅ Спортсмен {contact.first_name} зареєстрований.",
        reply_markup=start_kb
    )



# ──────────────────────── UTILITIES ────────────────────────

def parse_time(t: str) -> float:
    t = t.strip().replace(",", ".")
    if ":" in t:
        m, s = t.split(":", 1)
        return int(m) * 60 + float(s)
    return float(t)

def fmt_time(sec: float) -> str:
    m, s = divmod(sec, 60)
    return f"{int(m)}:{s:05.2f}" if m else f"{s:0.2f}"

def speed(dist: float, sec: float) -> float:
    return dist / sec if sec else 0.0

def get_segments(dist: int):
    if dist == 50:
        return [12.5, 12.5, 0, 12.5, 12.5]
    if dist == 100:
        return [25, 25, 25, 25]
    if dist == 200:
        return [50, 50, 50, 50]
    if dist >= 400:
        segs = [50] + [100] * ((dist - 50) // 100)
        rest = dist - sum(segs)
        if rest:
            segs.append(rest)
        return segs
    raise ValueError("unsupported distance")

def pr_key(uid: int, stroke: str, dist: int, idx: int) -> str:
    return f"{uid}|{stroke}|{dist}|{idx}"

# ───────────── FSM STATES ─────────────────────────────────
class AddResult(StatesGroup):
    choose_athlete = State()   # новый шаг: выбрать спортсмена
    choose_dist    = State()   # ввести дистанцию
    collect        = State()   # собирать времена сегментов

# ───────────────────────── HANDLERS ─────────────────────────
@dp.message(Command("reg"))
async def cmd_reg(message: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Перешли контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Перешлите контакт спортсмена:", reply_markup=kb)

@dp.message(lambda m: m.contact is not None)
async def reg_contact(message: types.Message):
    contact = message.contact
    # сохраняем в Google Sheets (AthletesList)
    ws_athletes.append_row([
        contact.user_id,
        contact.first_name or "",
        datetime.now(timezone.utc).isoformat(" ", "seconds")
    ])
    await message.answer(
        f"✅ Спортсмен {contact.first_name} зареєстрований.",
        reply_markup=start_kb
    )

@dp.message(Command("start"))
@dp.message(lambda m: m.text == "Старт")
async def cmd_start(message: types.Message):
    # главное меню
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Спринт",    callback_data="menu_sprint")],
    [InlineKeyboardButton(text="Стаер",     callback_data="menu_stayer")],
    [InlineKeyboardButton(text="История",   callback_data="menu_history")],
    [InlineKeyboardButton(text="Рекорды",   callback_data="menu_records")],
    *([ [InlineKeyboardButton(text="Admin", callback_data="menu_admin")] ]
      if message.from_user.id in ADMIN_IDS else [])
])
    await message.answer("Выбери раздел:", reply_markup=inline_kb)


@dp.callback_query(F.data == "add")
async def add(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("Введи дистанцію (50/100/200/400/800/1500):")
    await state.set_state(AddResult.choose_dist)

@dp.message(AddResult.choose_dist)
async def dist_chosen(m: types.Message, state: FSMContext):
    try:
        dist = int(m.text)
        if dist not in {50,100,200,400,800,1500}:
            raise ValueError
    except ValueError:
        return await m.reply("❗ Невірна дистанція. Спробуй ще.")
    await state.update_data(dist=dist, splits=[], idx=0)
    segs = get_segments(dist)
    await m.answer(f"Дистанція {dist} м. Час сегмента #1 ({segs[0]} м):")
    await state.set_state(AddResult.collect)

@dp.message(AddResult.collect)
async def collect(m: types.Message, state: FSMContext):
    data = await state.get_data()
    athlete_id = data.get("athlete_id")
    dist, idx, splits = data["dist"], data["idx"], data["splits"]
    segs = get_segments(dist)

    # парсим время сегмента
    try:
        t = parse_time(m.text)
    except Exception:
        return await m.reply("❗ Формат 0:32.45 або 32.45")
    splits.append(t)

    # если есть ещё сегменты — запрашиваем следующий
    if idx + 1 < len(segs):
        await state.update_data(idx=idx+1, splits=splits)
        await m.answer(f"Час сегмента #{idx+2} ({segs[idx+1]} м):")
        return

    # все сегменты введены — сбрасываем FSM
    await state.clear()

    # сохраняем результат
    total = sum(splits)
    stroke = "freestyle"
    now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
    ws_results.append_row([
        athlete_id,            # вместо m.from_user.id
        m.from_user.full_name, # можно заменить на имя из ws_athletes, если надо
        stroke,
        dist,
        now,
        json.dumps(splits),
        total
    ])

    # Логируем операцию
    ws_log.append_row([
        athlete_id, now, "ADD", json.dumps(splits)
    ])


    # обновляем PR в Sheets
    new_prs = []
    for i, seg_time in enumerate(splits):
        key = pr_key(m.from_user.id, stroke, dist, i)
        cell = ws_pr.find(key) if ws_pr.findall(key) else None
        if not cell:
            ws_pr.append_row([key, seg_time, now])
            new_prs.append((i, seg_time))
        else:
            old = float(ws_pr.cell(cell.row, 2).value.replace(",", "."))
            if seg_time < old:
                ws_pr.update_row(cell.row, [key, seg_time, now])
                new_prs.append((i, seg_time))

    # первый ответ — подтверждение и PR
    txt = f"✅ Збережено! Загальний час <b>{fmt_time(total)}</b>\n" \
          f"Середня швидкість {speed(dist, total):.2f} м/с"
    if new_prs:
        txt += "\n" + "\n".join(
            f"🥳 Новий PR сег #{i+1}: {fmt_time(t)}"
            for i, t in new_prs
        )
    await m.answer(txt)

    # логируем действие
    ws_log.append_row([m.from_user.id, now, "ADD", json.dumps(splits)])

    # ─────────────────── ANALYSIS ───────────────────
    seg_lens = get_segments(dist)
    speeds = [speed(seg, t) for seg, t in zip(seg_lens, splits)]
    avg_speed = speed(dist, total)
    pace = total / dist * 100
    degradation = ((speeds[0] - speeds[-1]) / speeds[0] * 100) if speeds and speeds[0] else 0

    analysis_text = (
        "📊 <b>Аналіз результату</b>\n"
        f"• Швидкості по сегментам: " + " • ".join(f"{v:.2f} м/с" for v in speeds) + "\n"
        f"• Середня швидкість: {avg_speed:.2f} м/с\n"
        f"• Темп: {pace:.1f} сек/100 м\n"
        f"• Деградація темпу: {degradation:.1f}%"
    )
    await m.answer(analysis_text)
    # ────────────────────────────────────────────────

@dp.callback_query(F.data == "history")
async def history(cb: CallbackQuery):
    rows = ws_results.get_all_values()[::-1]
    out = []
    for row in rows:
        if row and str(row[0]) == str(cb.from_user.id):
            dist = int(row[3]); splits = json.loads(row[5]); date = row[4]
            for i, t in enumerate(splits):
                out.append(f"{date} | {dist} м seg#{i+1}: {fmt_time(float(t))} ({speed(get_segments(dist)[i], float(t)):.2f} м/с)")
            if len(out) >= 30:
                break
    await cb.message.answer("\n".join(out) if out else "Поки історія пуста.")

@dp.callback_query(F.data == "records")
async def records(cb: CallbackQuery):
    rows = ws_pr.get_all_values()
    best = {}
    for row in rows:
        uid, _, dist, _ = row[0].split("|")
        if int(uid) == cb.from_user.id:
           best.setdefault(dist, []).append(float(row[1].replace(',', '.')))
    if not best:
        return await cb.message.answer("Ще нема рекордів.")
    lines = []
    for dist, arr in best.items():
        total = sum(arr)
        lines.append(f"🏅 {dist} м → {fmt_time(total)} (сума кращих)\n" + " • ".join(fmt_time(t) for t in arr))
    await cb.message.answer("\n\n".join(lines))

@dp.callback_query(F.data == "admin")
async def admin(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return
    await cb.message.answer("Адмін‑панель у процесі. Дані видно у Google Sheets.")

# ─────────────── Aliases для главного меню ───────────────
@dp.callback_query(F.data == "menu_sprint")
async def menu_sprint(cb: CallbackQuery, state: FSMContext):
    # получаем всех зарегистрированных спортсменов
    records = ws_athletes.get_all_records()
    kb = InlineKeyboardMarkup(row_width=2)
    for rec in records:
        # предполагаем, что ваш лист AthletesList имеет столбцы "ID" и "Name"
        athlete_id   = rec["ID"]
        athlete_name = rec.get("Name", str(athlete_id))
        kb.insert(
            InlineKeyboardButton(
                text=athlete_name,
                callback_data=f"select_{athlete_id}"
            )
        )
    await cb.message.answer("Выберите спортсмена:", reply_markup=kb)
    await state.set_state(AddResult.choose_athlete)

@dp.callback_query(F.data.startswith("select_"))
async def select_athlete(cb: CallbackQuery, state: FSMContext):
    # сохраняем выбранный ID в FSM
    athlete_id = int(cb.data.split("_", 1)[1])
    await state.update_data(athlete_id=athlete_id)
    # дальше спрашиваем дистанцию
    await cb.message.answer("Введите дистанцию (50/100/200/400/800/1500):")
    await state.set_state(AddResult.choose_dist)


@dp.callback_query(F.data == "menu_history")
async def menu_history(cb: CallbackQuery):
    await history(cb)

@dp.callback_query(F.data == "menu_records")
async def menu_records(cb: CallbackQuery):
    await records(cb)

@dp.callback_query(F.data == "menu_admin")
async def alias_admin(cb: CallbackQuery):
    await admin(cb)

@dp.callback_query(F.data == "menu_stayer")
async def menu_stayer(cb: CallbackQuery):
    await cb.message.answer("🚧 Блок «Стаер» ещё в разработке – скоро будет!")

# ───────────────────────── MAIN ─────────────────────────────
async def main():
    print("[SprintBot] starting…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
