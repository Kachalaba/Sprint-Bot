"""Async helpers for storing coach-athlete messages in SQLite."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

DB_PATH = Path("data/chat.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_SETUP_SCRIPT = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trainer_id INTEGER NOT NULL,
    athlete_id INTEGER NOT NULL,
    sender_role TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_by_trainer INTEGER NOT NULL DEFAULT 0,
    read_by_athlete INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_messages_trainer ON messages(trainer_id);
CREATE INDEX IF NOT EXISTS idx_messages_athlete ON messages(athlete_id);
CREATE INDEX IF NOT EXISTS idx_messages_pair ON messages(trainer_id, athlete_id, created_at);
"""


class ChatService:
    """Persist chat messages and provide simple aggregation helpers."""

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self.db_path = Path(db_path)
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        """Ensure database schema is ready."""

        async with self._lock:
            await asyncio.to_thread(self._setup)
            logger.info("Chat database initialised at %s", self.db_path)

    async def add_message(
        self,
        *,
        trainer_id: int,
        athlete_id: int,
        sender_role: str,
        text: str,
        created_at: datetime | None = None,
    ) -> None:
        """Append a new record and mark sender message as read for themselves."""

        stamp = (created_at or datetime.utcnow()).isoformat(sep=" ", timespec="seconds")
        read_flags = (
            1 if sender_role == "trainer" else 0,
            1 if sender_role == "athlete" else 0,
        )
        await asyncio.to_thread(
            self._execute,
            """
            INSERT INTO messages (
                trainer_id, athlete_id, sender_role, text, created_at,
                read_by_trainer, read_by_athlete
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trainer_id,
                athlete_id,
                sender_role,
                text,
                stamp,
                read_flags[0],
                read_flags[1],
            ),
        )

    async def list_threads(
        self, *, role: str, user_id: int
    ) -> Sequence[dict[str, Any]]:
        """Return thread summaries for trainer or athlete."""

        if role == "trainer":
            query = """
            SELECT
                athlete_id AS counterpart,
                MAX(created_at) AS last_at,
                SUM(CASE WHEN sender_role = 'athlete' AND read_by_trainer = 0 THEN 1 ELSE 0 END) AS unread,
                (
                    SELECT text
                    FROM messages m2
                    WHERE m2.trainer_id = m.trainer_id AND m2.athlete_id = m.athlete_id
                    ORDER BY m2.created_at DESC
                    LIMIT 1
                ) AS last_text
            FROM messages m
            WHERE trainer_id = ?
            GROUP BY athlete_id
            ORDER BY last_at DESC
            """
            params = (user_id,)
        else:
            query = """
            SELECT
                trainer_id AS counterpart,
                MAX(created_at) AS last_at,
                SUM(CASE WHEN sender_role = 'trainer' AND read_by_athlete = 0 THEN 1 ELSE 0 END) AS unread,
                (
                    SELECT text
                    FROM messages m2
                    WHERE m2.trainer_id = m.trainer_id AND m2.athlete_id = m.athlete_id
                    ORDER BY m2.created_at DESC
                    LIMIT 1
                ) AS last_text
            FROM messages m
            WHERE athlete_id = ?
            GROUP BY trainer_id
            ORDER BY last_at DESC
            """
            params = (user_id,)
        return await asyncio.to_thread(self._query_dicts, query, params)

    async def fetch_dialog(
        self,
        *,
        trainer_id: int,
        athlete_id: int,
        limit: int = 20,
    ) -> Sequence[dict[str, Any]]:
        """Load last messages for given pair ordered from oldest to newest."""

        rows = await asyncio.to_thread(
            self._query_dicts,
            """
            SELECT sender_role, text, created_at
            FROM messages
            WHERE trainer_id = ? AND athlete_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (trainer_id, athlete_id, limit),
        )
        return list(reversed(rows))

    async def mark_read(self, *, role: str, trainer_id: int, athlete_id: int) -> None:
        """Mark conversation messages as read for provided role."""

        if role == "trainer":
            query = (
                "UPDATE messages SET read_by_trainer = 1 "
                "WHERE trainer_id = ? AND athlete_id = ? AND sender_role = 'athlete' "
                "AND read_by_trainer = 0"
            )
        else:
            query = (
                "UPDATE messages SET read_by_athlete = 1 "
                "WHERE trainer_id = ? AND athlete_id = ? AND sender_role = 'trainer' "
                "AND read_by_athlete = 0"
            )
        await asyncio.to_thread(self._execute, query, (trainer_id, athlete_id))

    # --- sync helpers -----------------------------------------------------

    def _setup(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SETUP_SCRIPT)

    def _execute(self, query: str, params: Iterable[Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(query, tuple(params))
            conn.commit()

    def _query_dicts(self, query: str, params: Iterable[Any]) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
