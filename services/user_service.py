"""User profile storage and onboarding helpers."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_SETUP_SCRIPT = """
CREATE TABLE IF NOT EXISTS user_profiles (
    telegram_id INTEGER PRIMARY KEY,
    role TEXT NOT NULL,
    full_name TEXT NOT NULL,
    group_name TEXT DEFAULT NULL,
    language TEXT NOT NULL DEFAULT 'ru',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass(slots=True)
class UserProfile:
    """User profile stored in SQLite."""

    telegram_id: int
    role: str
    full_name: str
    group_name: Optional[str]
    language: str


class UserService:
    """Persist and retrieve user onboarding data."""

    def __init__(self, db_path: Path | str = Path("data/user_profiles.db")) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        """Initialise storage schema."""

        async with self._lock:
            await asyncio.to_thread(self._ensure_schema)

    async def get_profile(self, telegram_id: int) -> Optional[UserProfile]:
        """Return stored profile if present."""

        row = await asyncio.to_thread(self._fetch_profile, telegram_id)
        if row is None:
            return None
        return UserProfile(
            telegram_id=row["telegram_id"],
            role=row["role"],
            full_name=row["full_name"],
            group_name=row["group_name"],
            language=row["language"],
        )

    async def upsert_profile(
        self,
        telegram_id: int,
        *,
        role: str,
        full_name: str,
        language: str,
        group_name: Optional[str] = None,
    ) -> None:
        """Create or update profile data."""

        await asyncio.to_thread(
            self._upsert_profile,
            telegram_id,
            role,
            full_name,
            language,
            group_name,
        )

    async def update_language(self, telegram_id: int, language: str) -> None:
        """Update language preference for a user."""

        await asyncio.to_thread(self._update_field, telegram_id, "language", language)

    async def update_group(self, telegram_id: int, group_name: Optional[str]) -> None:
        """Update group/club for a user."""

        await asyncio.to_thread(self._update_field, telegram_id, "group_name", group_name)

    async def update_name(self, telegram_id: int, full_name: str) -> None:
        """Update full name for a user."""

        await asyncio.to_thread(self._update_field, telegram_id, "full_name", full_name)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SETUP_SCRIPT)
            conn.commit()

    def _fetch_profile(self, telegram_id: int) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT telegram_id, role, full_name, group_name, language FROM user_profiles WHERE telegram_id = ?",
                (telegram_id,),
            )
            return cursor.fetchone()

    def _upsert_profile(
        self,
        telegram_id: int,
        role: str,
        full_name: str,
        language: str,
        group_name: Optional[str],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (telegram_id, role, full_name, language, group_name)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    role = excluded.role,
                    full_name = excluded.full_name,
                    language = excluded.language,
                    group_name = excluded.group_name,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (telegram_id, role, full_name, language, group_name),
            )
            conn.commit()

    def _update_field(self, telegram_id: int, field: str, value: Optional[str]) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE user_profiles
                SET {field} = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
                """,
                (value, telegram_id),
            )
            conn.commit()
