import logging
import os
from functools import lru_cache

import gspread
from aiogram import Bot
from dotenv import load_dotenv

# --- Environment setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

# --- Bot Initialization ---
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN must be set in .env file")
bot = Bot(token=TOKEN, parse_mode="HTML")


# --- Google Sheets Setup ---
try:
    gc = gspread.service_account(filename="creds.json")
    sh = gc.open_by_key(os.getenv("SPREADSHEET_KEY"))

    # Assign worksheets to variables
    ws_results = sh.worksheet("results")
    ws_pr = sh.worksheet("pr")
    ws_log = sh.worksheet("log")
    ws_athletes = sh.worksheet("AthletesList")  # Corrected worksheet name

except gspread.exceptions.SpreadsheetNotFound:
    logging.error("Spreadsheet not found. Check SPREADSHEET_KEY in .env file.")
    raise
except gspread.exceptions.WorksheetNotFound as e:
    logging.error(
        f"Worksheet not found: {e}. Make sure all worksheets (results, pr, log, AthletesList) exist."
    )
    raise
except Exception as e:
    logging.error(f"An error occurred during Google Sheets initialization: {e}")
    raise

# --- Constants and Helpers ---
ADMIN_IDS = (os.getenv("ADMIN_IDS") or "").split(",")


@lru_cache(maxsize=1)
def get_all_sportsmen() -> list[str]:
    """Get a list of all sportsmen's names."""
    try:
        # Assuming names are in the second column (B) starting from the second row
        return ws_athletes.col_values(2)[1:]
    except Exception as e:
        logging.error(f"Failed to get sportsmen list from Google Sheets: {e}")
        return []
