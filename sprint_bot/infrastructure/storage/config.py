"""Configuration helpers for selecting storage backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping


class StorageBackend(str, Enum):
    """Supported storage backends for domain repositories."""

    SHEETS = "sheets"
    POSTGRES = "postgres"


@dataclass(slots=True)
class StorageSettings:
    """Strongly-typed settings for storage layer wiring."""

    backend: StorageBackend = StorageBackend.SHEETS
    spreadsheet_key: str | None = None
    credentials_path: Path = Path("creds.json")
    db_url: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "StorageSettings":
        """Build settings instance from environment variables."""

        data = environ or os.environ
        backend_raw = (data.get("STORAGE_BACKEND") or StorageBackend.SHEETS.value).lower()
        try:
            backend = StorageBackend(backend_raw)
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise ValueError(
                f"Unsupported STORAGE_BACKEND '{backend_raw}'. Use 'sheets' or 'postgres'."
            ) from exc

        spreadsheet_key = data.get("SPREADSHEET_KEY") or None
        db_url = data.get("DB_URL") or None
        credentials_path_raw = data.get("GOOGLE_APPLICATION_CREDENTIALS") or data.get("SHEETS_CREDENTIALS")
        credentials_path = Path(credentials_path_raw) if credentials_path_raw else Path("creds.json")

        return cls(
            backend=backend,
            spreadsheet_key=spreadsheet_key,
            credentials_path=credentials_path,
            db_url=db_url,
        )

    def require_spreadsheet_key(self) -> str:
        """Return spreadsheet key ensuring it is provided."""

        if not self.spreadsheet_key:
            raise RuntimeError(
                "SPREADSHEET_KEY must be configured to use the Google Sheets storage backend."
            )
        return self.spreadsheet_key

    def require_db_url(self) -> str:
        """Return Postgres connection string ensuring it is present."""

        if not self.db_url:
            raise RuntimeError("DB_URL must be configured to use the Postgres storage backend.")
        return self.db_url
