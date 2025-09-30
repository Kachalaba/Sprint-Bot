"""Role management utilities for Sprint Bot."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from aiogram.types import Contact, User

ROLE_ATHLETE = "athlete"
ROLE_TRAINER = "trainer"
ROLE_ADMIN = "admin"
VALID_ROLES = (ROLE_ATHLETE, ROLE_TRAINER, ROLE_ADMIN)


@dataclass(frozen=True)
class RoleUser:
    """Representation of a user and their role."""

    telegram_id: int
    full_name: str
    role: str

    @property
    def short_label(self) -> str:
        """Return readable label used in admin lists."""

        name = self.full_name or f"ID {self.telegram_id}"
        return f"{name} ({self.telegram_id})"


class RoleService:
    """Persist user roles and trainer-athlete relationships."""

    def __init__(self, db_path: Path | str = Path("data/roles.db")) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def init(self, *, admin_ids: Iterable[int] = ()) -> None:
        """Ensure schema exists and preload default admins."""

        async with self._lock:
            await asyncio.to_thread(self._setup, tuple(admin_ids))

    async def upsert_user(
        self, user: User | Contact | None, *, default_role: str = ROLE_ATHLETE
    ) -> None:
        """Ensure user exists in storage keeping latest full name."""

        if user is None:
            return
        user_id = getattr(user, "id", None) or getattr(user, "user_id", None)
        if user_id is None:
            return
        full_name = getattr(user, "full_name", None) or getattr(user, "first_name", "")
        last_name = getattr(user, "last_name", None)
        if last_name:
            full_name = f"{full_name} {last_name}".strip()
        await asyncio.to_thread(
            self._upsert_user, int(user_id), full_name or "", default_role
        )

    async def bulk_sync_athletes(self, records: Iterable[tuple[int, str]]) -> None:
        """Synchronise athlete records from Google Sheets."""

        await asyncio.to_thread(self._bulk_sync_athletes, tuple(records))

    async def set_role(self, user_id: int, role: str) -> None:
        """Assign role to user creating the record if required."""

        if role not in VALID_ROLES:
            raise ValueError(f"Unsupported role: {role}")
        await asyncio.to_thread(self._set_role, user_id, role)

    async def get_role(self, user_id: int) -> str:
        """Return stored role or default athlete if user is unknown."""

        return await asyncio.to_thread(self._get_role, user_id)

    async def list_users(
        self, roles: Iterable[str] | None = None
    ) -> Sequence[RoleUser]:
        """Return users filtered by roles (all by default)."""

        return await asyncio.to_thread(
            self._list_users, tuple(roles) if roles else None
        )

    async def set_trainer(self, athlete_id: int, trainer_id: int) -> None:
        """Assign primary trainer for athlete (overrides previous)."""

        await asyncio.to_thread(self._set_trainer, athlete_id, trainer_id)

    async def trainers_for_athlete(self, athlete_id: int) -> Sequence[int]:
        """Return trainer ids linked to athlete."""

        return await asyncio.to_thread(self._trainers_for_athlete, athlete_id)

    async def athletes_for_trainer(self, trainer_id: int) -> Sequence[int]:
        """Return athlete ids linked to trainer."""

        return await asyncio.to_thread(self._athletes_for_trainer, trainer_id)

    async def get_accessible_athletes(self, requester_id: int) -> Sequence[int]:
        """Return athlete ids the requester is allowed to manage."""

        role = await self.get_role(requester_id)
        if role in {ROLE_ADMIN, ROLE_TRAINER}:
            athletes = await self.list_users(roles=(ROLE_ATHLETE,))
            return tuple(user.telegram_id for user in athletes)
        return (requester_id,)

    async def can_access_athlete(self, requester_id: int, athlete_id: int) -> bool:
        """Check if requester has permission to view athlete data."""

        if requester_id == athlete_id:
            return True
        role = await self.get_role(requester_id)
        if role == ROLE_ADMIN:
            return True
        if role == ROLE_TRAINER:
            return True
        trainers = await self.trainers_for_athlete(athlete_id)
        return requester_id in trainers

    # --- synchronous helpers --------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _setup(self, admin_ids: Sequence[int]) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    full_name TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'athlete',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS trainer_athletes (
                    athlete_id INTEGER NOT NULL,
                    trainer_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (athlete_id, trainer_id)
                );
                """
            )
            for admin_id in admin_ids:
                if not admin_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO users (telegram_id, full_name, role)
                    VALUES (?, '', ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET role = excluded.role,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (admin_id, ROLE_ADMIN),
                )
            conn.commit()

    def _upsert_user(self, user_id: int, full_name: str, default_role: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (telegram_id, full_name, role)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, full_name, default_role),
            )
            conn.commit()

    def _bulk_sync_athletes(self, records: Sequence[tuple[int, str]]) -> None:
        if not records:
            return
        with self._connect() as conn:
            for athlete_id, name in records:
                conn.execute(
                    """
                    INSERT INTO users (telegram_id, full_name, role)
                    VALUES (?, ?, ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET
                        full_name = excluded.full_name,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (athlete_id, name, ROLE_ATHLETE),
                )
            conn.commit()

    def _set_role(self, user_id: int, role: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (telegram_id, full_name, role)
                VALUES (?, '', ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    role = excluded.role,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, role),
            )
            conn.commit()

    def _get_role(self, user_id: int) -> str:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT role FROM users WHERE telegram_id = ?", (user_id,)
            )
            row = cur.fetchone()
            return row["role"] if row else ROLE_ATHLETE

    def _list_users(self, roles: Sequence[str] | None) -> Sequence[RoleUser]:
        query = "SELECT telegram_id, full_name, role FROM users"
        params: tuple[object, ...] = ()
        if roles:
            placeholders = ",".join(["?"] * len(roles))
            query += f" WHERE role IN ({placeholders})"
            params = tuple(roles)
        query += " ORDER BY role, full_name, telegram_id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                RoleUser(
                    telegram_id=row["telegram_id"],
                    full_name=row["full_name"],
                    role=row["role"],
                )
                for row in rows
            ]

    def _set_trainer(self, athlete_id: int, trainer_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM trainer_athletes WHERE athlete_id = ?",
                (athlete_id,),
            )
            conn.execute(
                """
                INSERT INTO trainer_athletes (athlete_id, trainer_id)
                VALUES (?, ?)
                """,
                (athlete_id, trainer_id),
            )
            conn.commit()

    def _trainers_for_athlete(self, athlete_id: int) -> Sequence[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT trainer_id FROM trainer_athletes WHERE athlete_id = ?",
                (athlete_id,),
            ).fetchall()
            return tuple(row["trainer_id"] for row in rows)

    def _athletes_for_trainer(self, trainer_id: int) -> Sequence[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT athlete_id FROM trainer_athletes WHERE trainer_id = ?",
                (trainer_id,),
            ).fetchall()
            return tuple(row["athlete_id"] for row in rows)
