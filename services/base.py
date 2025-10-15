"""Legacy service initialisation utilities."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, cast

import gspread
from aiogram import Bot
from dotenv import load_dotenv

# --- Environment setup ---
load_dotenv()

logger = logging.getLogger(__name__)

# --- Bot Initialization ---


@lru_cache(maxsize=1)
def get_bot() -> Bot:
    """Return a cached aiogram Bot instance configured for the project."""

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN environment variable must be set and non-empty to create the bot."
        )
    return Bot(token=token, parse_mode="HTML")


def _get_credentials_path() -> Path:
    return Path("creds.json")


@lru_cache(maxsize=1)
def _get_gspread_client() -> gspread.Client:
    """Return a cached gspread client configured via ``creds.json``."""

    creds_path = _get_credentials_path()
    if not creds_path.exists():
        raise RuntimeError(
            "Google credentials file 'creds.json' is required. Place the service account "
            "JSON next to the application or update the path in services.base."
        )
    try:
        return gspread.service_account(filename=str(creds_path))
    except Exception as exc:  # pragma: no cover - depends on external file state
        raise RuntimeError(
            "Failed to load Google credentials from 'creds.json'. Verify that the file "
            "contains a valid service account key."
        ) from exc


def _get_spreadsheet_key() -> str:
    """Return validated spreadsheet key from environment."""

    key = os.getenv("SPREADSHEET_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "SPREADSHEET_KEY environment variable must be set to access Google Sheets."
        )
    return key


@lru_cache(maxsize=1)
def get_spreadsheet() -> gspread.Spreadsheet:
    """Open and cache the configured Google Spreadsheet."""

    key = _get_spreadsheet_key()
    try:
        client = _get_gspread_client()
        return client.open_by_key(key)
    except gspread.exceptions.SpreadsheetNotFound as exc:
        raise RuntimeError(
            f"Spreadsheet with key '{key}' was not found. Verify SPREADSHEET_KEY and "
            "ensure the service account has access."
        ) from exc
    except (
        gspread.exceptions.GSpreadException
    ) as exc:  # pragma: no cover - network errors
        raise RuntimeError(
            "Unable to open the Google Spreadsheet. Check credentials and network access."
        ) from exc


@lru_cache(maxsize=None)
def get_worksheet(name: str) -> gspread.Worksheet:
    """Return a worksheet by name from the configured spreadsheet."""

    try:
        spreadsheet = get_spreadsheet()
        return spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound as exc:
        raise RuntimeError(
            f"Worksheet '{name}' was not found. Create it in the spreadsheet or update the "
            "configuration."
        ) from exc
    except (
        gspread.exceptions.GSpreadException
    ) as exc:  # pragma: no cover - network errors
        raise RuntimeError(
            f"Unable to access worksheet '{name}'. Check spreadsheet availability."
        ) from exc


def get_results_worksheet() -> gspread.Worksheet:
    """Return the worksheet that stores swim results."""

    return get_worksheet("results")


def get_pr_worksheet() -> gspread.Worksheet:
    """Return the worksheet that stores personal records."""

    return get_worksheet("pr")


def get_log_worksheet() -> gspread.Worksheet:
    """Return the worksheet used for action logging."""

    return get_worksheet("log")


def get_athletes_worksheet() -> gspread.Worksheet:
    """Return the worksheet with the list of registered athletes."""

    return get_worksheet("AthletesList")


# --- Constants and Helpers ---
ADMIN_IDS = (os.getenv("ADMIN_IDS") or "").split(",")


@lru_cache(maxsize=1)
def get_all_sportsmen() -> list[str]:
    """Get a list of all sportsmen's names."""

    try:
        worksheet = get_athletes_worksheet()
    except RuntimeError as exc:
        logger.error("Unable to access athletes worksheet: %s", exc)
        return []

    try:
        # Assuming names are in the second column (B) starting from the second row
        values = cast(list[str], worksheet.col_values(2))
        return values[1:]
    except (
        gspread.exceptions.GSpreadException
    ) as e:  # pragma: no cover - relies on external service
        logger.error("Failed to get sportsmen list from Google Sheets: %s", e)
        return []


def get_registered_athletes() -> list[tuple[int, str]]:
    """Return registered athletes as tuples of (telegram_id, name)."""

    try:
        worksheet = get_athletes_worksheet()
    except RuntimeError as exc:
        logger.error("Unable to access athletes worksheet: %s", exc)
        return []

    try:
        rows = worksheet.get_all_values()
    except (
        gspread.exceptions.GSpreadException
    ) as e:  # pragma: no cover - relies on external service
        logger.error("Failed to fetch athletes: %s", e)
        return []

    athletes: list[tuple[int, str]] = []
    for raw in rows[1:]:
        if not raw:
            continue
        try:
            athlete_id = int(raw[0])
        except (ValueError, TypeError, IndexError):
            continue
        name = raw[1] if len(raw) > 1 and raw[1] else "Без імені"
        athletes.append((athlete_id, name))
    return athletes


def get_athlete_name(athlete_id: int) -> Optional[str]:
    """Return athlete name by telegram id if registered."""

    for uid, name in get_registered_athletes():
        if uid == athlete_id:
            return name
    return None
