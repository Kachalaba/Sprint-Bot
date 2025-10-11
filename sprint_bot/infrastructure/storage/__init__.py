"""Storage facade wiring for Google Sheets and Postgres backends."""

from __future__ import annotations

from sprint_bot.application.ports.storage import Storage

from .config import StorageBackend, StorageSettings
from .google_sheets import GoogleSheetsStorage
from .postgres import PostgresStorage

__all__ = [
    "StorageBackend",
    "StorageSettings",
    "GoogleSheetsStorage",
    "PostgresStorage",
    "create_storage",
]


async def create_storage(settings: StorageSettings) -> Storage:
    """Instantiate storage backend based on provided settings."""

    if settings.backend == StorageBackend.SHEETS:
        storage = GoogleSheetsStorage(
            spreadsheet_key=settings.require_spreadsheet_key(),
            credentials_path=settings.credentials_path,
        )
    elif settings.backend == StorageBackend.POSTGRES:
        storage = PostgresStorage(database_url=settings.require_db_url())
    else:  # pragma: no cover - defensive default
        raise ValueError(f"Unsupported storage backend: {settings.backend}")

    await storage.init()
    return storage
