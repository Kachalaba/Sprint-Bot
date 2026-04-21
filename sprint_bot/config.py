"""Centralised application settings backed by ``pydantic-settings``.

This module exposes a single :class:`Settings` instance returned by
:func:`get_settings`.  Every environment variable used by the bot must be
declared here so that call sites can consume a strongly-typed object instead
of sprinkling ``os.getenv`` across modules.
"""

from __future__ import annotations

from datetime import time, timedelta
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Tuple  # noqa: F401  # re-exported alias for QuietHoursWindow

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageBackend(str, Enum):
    """Supported storage backends for domain repositories."""

    SHEETS = "sheets"
    POSTGRES = "postgres"


QuietHoursWindow = Tuple[time, time]


def _parse_quiet_hours(value: str) -> QuietHoursWindow:
    parts = [chunk.strip() for chunk in value.split("-", 1)]
    if len(parts) != 2:
        raise ValueError("QUIET_HOURS must be formatted as HH:MM-HH:MM")
    start_raw, end_raw = parts
    if not start_raw or not end_raw:
        raise ValueError("QUIET_HOURS must include both start and end times")
    return time.fromisoformat(start_raw), time.fromisoformat(end_raw)


class Settings(BaseSettings):
    """Strongly-typed runtime configuration for Sprint Bot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Telegram -------------------------------------------------------
    bot_token: str = Field(default="", alias="BOT_TOKEN")
    admin_ids_raw: str = Field(default="", alias="ADMIN_IDS")

    # --- Environment / observability -----------------------------------
    env: str = Field(default="development", alias="ENV")
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")

    # --- Storage --------------------------------------------------------
    storage_backend: StorageBackend = Field(
        default=StorageBackend.SHEETS, alias="STORAGE_BACKEND"
    )
    spreadsheet_key: str | None = Field(default=None, alias="SPREADSHEET_KEY")
    db_url: str | None = Field(default=None, alias="DB_URL")
    google_credentials_path: Path = Field(
        default=Path("creds.json"), alias="GOOGLE_APPLICATION_CREDENTIALS"
    )
    chat_db_path: Path = Field(default=Path("data/chat.db"), alias="CHAT_DB_PATH")

    # --- Notifications --------------------------------------------------
    quiet_hours: str | None = Field(default=None, alias="QUIET_HOURS")
    quiet_queue_interval: float = Field(default=60.0, alias="QUIET_QUEUE_INTERVAL")
    quiet_hours_tz: str = Field(default="Europe/Kyiv", alias="QUIET_HOURS_TZ")

    # --- Analytics ------------------------------------------------------
    turn_analysis_default_stroke: str = Field(
        default="breaststroke", alias="TURN_ANALYSIS_DEFAULT_STROKE"
    )

    # --- Backups --------------------------------------------------------
    s3_backup_bucket: str = Field(default="", alias="S3_BACKUP_BUCKET")
    s3_backup_prefix: str = Field(
        default="sprint-bot/backups/", alias="S3_BACKUP_PREFIX"
    )
    s3_storage_class: str | None = Field(default=None, alias="S3_STORAGE_CLASS")
    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")
    backup_interval_hours: float = Field(default=6.0, alias="BACKUP_INTERVAL_HOURS")

    @field_validator("storage_backend", mode="before")
    @classmethod
    def _normalise_backend(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower()
        return value

    @field_validator(
        "spreadsheet_key",
        "db_url",
        "s3_storage_class",
        "s3_endpoint_url",
        "sentry_dsn",
        mode="before",
    )
    @classmethod
    def _empty_as_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    # --- Derived helpers ------------------------------------------------
    @computed_field  # type: ignore[misc]
    @property
    def admin_ids(self) -> tuple[int, ...]:
        """Parsed ``ADMIN_IDS`` — comma separated integers.

        Invalid entries are skipped silently (they are logged at service boot
        by callers that iterate over the raw value).
        """

        parsed: list[int] = []
        for item in self.admin_ids_raw.split(","):
            text = item.strip()
            if not text:
                continue
            try:
                parsed.append(int(text))
            except ValueError:
                continue
        return tuple(parsed)

    @property
    def backup_interval(self) -> timedelta:
        """Backup interval validated to be strictly positive."""

        hours = self.backup_interval_hours if self.backup_interval_hours > 0 else 6.0
        return timedelta(hours=hours)

    @property
    def quiet_hours_window(self) -> QuietHoursWindow | None:
        """Parsed quiet hours window or ``None`` when disabled/invalid."""

        if not self.quiet_hours:
            return None
        try:
            return _parse_quiet_hours(self.quiet_hours)
        except ValueError:
            return None

    def require_bot_token(self) -> str:
        """Return bot token, raising if missing — used during bot construction."""

        token = self.bot_token.strip()
        if not token:
            raise RuntimeError(
                "BOT_TOKEN environment variable must be set and non-empty."
            )
        return token

    def require_spreadsheet_key(self) -> str:
        """Return spreadsheet key or raise — used by the Sheets backend."""

        if not self.spreadsheet_key:
            raise RuntimeError(
                "SPREADSHEET_KEY must be configured to use the Google Sheets backend."
            )
        return self.spreadsheet_key

    def require_db_url(self) -> str:
        """Return Postgres URL or raise — used by the Postgres backend."""

        if not self.db_url:
            raise RuntimeError(
                "DB_URL must be configured to use the Postgres storage backend."
            )
        return self.db_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance built from the environment."""

    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached settings instance (useful for tests)."""

    get_settings.cache_clear()
