"""Batch import from Google Sheets storage into Postgres."""

from __future__ import annotations

import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from sprint_bot.infrastructure.storage import (
    GoogleSheetsStorage,
    PostgresStorage,
    StorageBackend,
    StorageSettings,
)

LOG_PATH = Path("logs/bot.log")


def setup_logging() -> None:
    """Configure logging handlers according to project standards."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    stderr_handler = logging.StreamHandler()
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))

    logger.handlers = [file_handler, stderr_handler]


async def import_data() -> None:
    """Import entities from Google Sheets into Postgres in an idempotent fashion."""

    load_dotenv()
    setup_logging()
    logger = logging.getLogger("import")

    env = os.environ
    sheets_settings = StorageSettings(
        backend=StorageBackend.SHEETS,
        spreadsheet_key=env.get("SPREADSHEET_KEY"),
        credentials_path=Path(env.get("GOOGLE_APPLICATION_CREDENTIALS") or "creds.json"),
    )
    postgres_settings = StorageSettings(
        backend=StorageBackend.POSTGRES,
        db_url=env.get("DB_URL"),
    )

    sheets_storage = GoogleSheetsStorage(
        spreadsheet_key=sheets_settings.require_spreadsheet_key(),
        credentials_path=sheets_settings.credentials_path,
    )
    postgres_storage = PostgresStorage(database_url=postgres_settings.require_db_url())

    await sheets_storage.init()
    await postgres_storage.init()

    try:
        await _import_coaches(sheets_storage, postgres_storage, logger)
        await _import_athletes(sheets_storage, postgres_storage, logger)
        await _import_races(sheets_storage, postgres_storage, logger)
        await _import_records(sheets_storage, postgres_storage, logger)
    finally:
        await sheets_storage.close()
        await postgres_storage.close()


async def _import_coaches(
    sheets: GoogleSheetsStorage,
    postgres: PostgresStorage,
    logger: logging.Logger,
) -> None:
    coaches = await sheets.coaches.list_active()
    for coach in coaches:
        await postgres.coaches.upsert(coach)
    logger.info("Imported %d coaches", len(coaches))


async def _import_athletes(
    sheets: GoogleSheetsStorage,
    postgres: PostgresStorage,
    logger: logging.Logger,
) -> None:
    athletes = await sheets.athletes.list_active()
    for athlete in athletes:
        await postgres.athletes.upsert(athlete)
    logger.info("Imported %d athletes", len(athletes))


async def _import_races(
    sheets: GoogleSheetsStorage,
    postgres: PostgresStorage,
    logger: logging.Logger,
) -> None:
    races = await sheets.results.list_recent(limit=0)
    imported = 0
    for race in races:
        try:
            await postgres.results.save(race)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to import race %s", race.id)
        else:
            imported += 1
    logger.info("Imported %d of %d races", imported, len(races))


async def _import_records(
    sheets: GoogleSheetsStorage,
    postgres: PostgresStorage,
    logger: logging.Logger,
) -> None:
    athletes = await sheets.athletes.list_active()
    total_prs = 0
    for athlete in athletes:
        prs = await sheets.records.list_segment_prs(athlete.id)
        for record in prs:
            await postgres.records.upsert_segment_pr(record)
            total_prs += 1
        sob = await sheets.records.get_sob(athlete.id)
        if sob:
            await postgres.records.save_sob(sob)
    logger.info("Imported %d segment PRs and SoB snapshots for %d athletes", total_prs, len(athletes))


def main() -> None:
    asyncio.run(import_data())


if __name__ == "__main__":
    main()
