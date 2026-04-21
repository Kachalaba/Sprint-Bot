"""Tests for :mod:`sprint_bot.config`."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from sprint_bot.config import Settings, StorageBackend, get_settings, reset_settings_cache


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every env var the :class:`Settings` cares about."""

    for name in (
        "BOT_TOKEN",
        "ADMIN_IDS",
        "ENV",
        "SENTRY_DSN",
        "STORAGE_BACKEND",
        "SPREADSHEET_KEY",
        "DB_URL",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "CHAT_DB_PATH",
        "QUIET_HOURS",
        "QUIET_QUEUE_INTERVAL",
        "QUIET_HOURS_TZ",
        "TURN_ANALYSIS_DEFAULT_STROKE",
        "S3_BACKUP_BUCKET",
        "S3_BACKUP_PREFIX",
        "S3_STORAGE_CLASS",
        "S3_ENDPOINT_URL",
        "BACKUP_INTERVAL_HOURS",
    ):
        monkeypatch.delenv(name, raising=False)


def _settings_without_env_file(**overrides: object) -> Settings:
    """Build Settings instance ignoring any ``.env`` in the repo root."""

    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_defaults_without_env(clean_env: None) -> None:
    settings = _settings_without_env_file()

    assert settings.bot_token == ""
    assert settings.admin_ids == ()
    assert settings.env == "development"
    assert settings.storage_backend is StorageBackend.SHEETS
    assert settings.spreadsheet_key is None
    assert settings.db_url is None
    assert settings.google_credentials_path == Path("creds.json")
    assert settings.chat_db_path == Path("data/chat.db")
    assert settings.quiet_queue_interval == 60.0
    assert settings.quiet_hours_tz == "Europe/Kyiv"
    assert settings.turn_analysis_default_stroke == "breaststroke"
    assert settings.backup_interval == dt.timedelta(hours=6)
    assert settings.quiet_hours_window is None


def test_admin_ids_parses_csv(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_IDS", " 123, 456,789, , 10 ")

    settings = _settings_without_env_file()

    assert settings.admin_ids == (123, 456, 789, 10)


def test_admin_ids_skips_invalid_entries(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_IDS", "123,abc,42")

    settings = _settings_without_env_file()

    assert settings.admin_ids == (123, 42)


def test_quiet_hours_window_parsed(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QUIET_HOURS", "22:00-07:30")

    settings = _settings_without_env_file()

    assert settings.quiet_hours_window == (dt.time(22, 0), dt.time(7, 30))


def test_quiet_hours_window_invalid_returns_none(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QUIET_HOURS", "nonsense")

    settings = _settings_without_env_file()

    assert settings.quiet_hours_window is None


def test_storage_backend_normalised(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "POSTGRES")

    settings = _settings_without_env_file()

    assert settings.storage_backend is StorageBackend.POSTGRES


def test_empty_strings_treated_as_none(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SPREADSHEET_KEY", "   ")
    monkeypatch.setenv("DB_URL", "")
    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    monkeypatch.setenv("SENTRY_DSN", "")

    settings = _settings_without_env_file()

    assert settings.spreadsheet_key is None
    assert settings.db_url is None
    assert settings.s3_endpoint_url is None
    assert settings.sentry_dsn is None


def test_require_bot_token_raises_when_missing(clean_env: None) -> None:
    settings = _settings_without_env_file()

    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        settings.require_bot_token()


def test_require_bot_token_returns_value(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOT_TOKEN", "  abc:123  ")

    settings = _settings_without_env_file()

    assert settings.require_bot_token() == "abc:123"


def test_require_spreadsheet_key_raises_when_missing(clean_env: None) -> None:
    settings = _settings_without_env_file()

    with pytest.raises(RuntimeError, match="SPREADSHEET_KEY"):
        settings.require_spreadsheet_key()


def test_require_db_url_raises_when_missing(clean_env: None) -> None:
    settings = _settings_without_env_file()

    with pytest.raises(RuntimeError, match="DB_URL"):
        settings.require_db_url()


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token-one")
    reset_settings_cache()
    first = get_settings()

    monkeypatch.setenv("BOT_TOKEN", "token-two")
    second = get_settings()

    assert first is second

    reset_settings_cache()
    third = get_settings()

    assert third is not first
    assert third.bot_token == "token-two"


def test_non_positive_backup_interval_falls_back(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKUP_INTERVAL_HOURS", "0")

    settings = _settings_without_env_file()

    assert settings.backup_interval == dt.timedelta(hours=6)
