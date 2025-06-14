from __future__ import annotations

import os
from datetime import datetime, timezone

import gspread
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise SystemExit("⛔ Переменная BOT_TOKEN не задана. См. .env.example")

ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "597164575").split(",") if x}

CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "creds.json")
SPREADSHEET_KEY = os.getenv(
    "SPREADSHEET_KEY", "1NA-BcyS4QQjMdnDi-jxM91qDIvwj43Z50bsjRph2UtU"
)

if not os.path.exists(CREDENTIALS_FILE):
    raise SystemExit(f"⛔ Не найден {CREDENTIALS_FILE}. Помести JSON рядом с bot.py")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
try:
    book = client.open_by_key(SPREADSHEET_KEY)
except Exception as exc:
    raise SystemExit(
        "⛔ Таблица с таким ключом не найдена или нет доступа. Проверь Share."
    ) from exc

sheet_titles = {ws.title for ws in book.worksheets()}
for title in ("ATHLETES", "PR", "LOG"):
    if title not in sheet_titles:
        book.add_worksheet(title, rows="1000", cols="10")

ws_results = book.worksheet("ATHLETES")
ws_pr = book.worksheet("PR")
ws_log = book.worksheet("LOG")

if "AthletesList" not in sheet_titles:
    book.add_worksheet("AthletesList", rows="1000", cols="3")
ws_athletes = book.worksheet("AthletesList")

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
