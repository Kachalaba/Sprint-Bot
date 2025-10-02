"""Audit log service with undo support for results and templates."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence, Literal

ActionType = Literal["create", "update", "delete"]
EntityType = Literal["result", "template"]


@dataclass(slots=True, frozen=True)
class AuditEntry:
    """Single audit log record."""

    id: int
    user_id: int
    action: str
    entity_type: str
    entity_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    ts: datetime


class AuditService:
    """Manage audit log entries and undo operations."""

    _MIGRATION_PATH = Path("db/migrations/001_create_audit_log.sql")

    def __init__(
        self,
        *,
        results_db_path: Path | str = Path("data/results.db"),
        template_path: Path | str = Path("data/sprint_templates.json"),
    ) -> None:
        self._db_path = Path(results_db_path)
        self._template_path = Path(template_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._template_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        """Ensure audit schema exists."""

        async with self._lock:
            await asyncio.to_thread(self._ensure_schema)

    async def log_result_create(self, *, actor_id: int, result: Mapping[str, Any]) -> None:
        await self._record(
            actor_id=actor_id,
            action="create",
            entity_type="result",
            entity_id=str(result.get("id")),
            before=None,
            after=result,
        )

    async def log_result_update(
        self,
        *,
        actor_id: int,
        entity_id: int,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
    ) -> None:
        await self._record(
            actor_id=actor_id,
            action="update",
            entity_type="result",
            entity_id=str(entity_id),
            before=before,
            after=after,
        )

    async def log_result_delete(
        self,
        *,
        actor_id: int,
        result: Mapping[str, Any],
    ) -> None:
        await self._record(
            actor_id=actor_id,
            action="delete",
            entity_type="result",
            entity_id=str(result.get("id")),
            before=result,
            after=None,
        )

    async def log_template_create(
        self,
        *,
        actor_id: int,
        template_id: str,
        after: Mapping[str, Any],
    ) -> None:
        await self._record(
            actor_id=actor_id,
            action="create",
            entity_type="template",
            entity_id=template_id,
            before=None,
            after=after,
        )

    async def log_template_update(
        self,
        *,
        actor_id: int,
        template_id: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
    ) -> None:
        await self._record(
            actor_id=actor_id,
            action="update",
            entity_type="template",
            entity_id=template_id,
            before=before,
            after=after,
        )

    async def log_template_delete(
        self,
        *,
        actor_id: int,
        template_id: str,
        before: Mapping[str, Any],
    ) -> None:
        await self._record(
            actor_id=actor_id,
            action="delete",
            entity_type="template",
            entity_id=template_id,
            before=before,
            after=None,
        )

    async def list_entries(
        self,
        *,
        limit: int = 10,
        user_id: int | None = None,
    ) -> tuple[AuditEntry, ...]:
        return await asyncio.to_thread(self._fetch_entries, limit, user_id)

    async def undo(self, op_id: int) -> bool:
        entry = await asyncio.to_thread(self._fetch_entry, op_id)
        if entry is None:
            return False
        if entry.entity_type == "result":
            return await asyncio.to_thread(self._undo_result, entry)
        if entry.entity_type == "template":
            return await asyncio.to_thread(self._undo_template, entry)
        return False

    # --- internal helpers -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        script = self._MIGRATION_PATH.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(script)
            conn.commit()

    async def _record(
        self,
        *,
        actor_id: int,
        action: str,
        entity_type: str,
        entity_id: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
    ) -> None:
        if actor_id <= 0:
            raise ValueError("actor_id must be positive")
        payload_before = json.dumps(before, ensure_ascii=False, sort_keys=True) if before else None
        payload_after = json.dumps(after, ensure_ascii=False, sort_keys=True) if after else None
        timestamp = datetime.now(UTC).isoformat(timespec="seconds")
        await asyncio.to_thread(
            self._insert_record,
            actor_id,
            action,
            entity_type,
            entity_id,
            payload_before,
            payload_after,
            timestamp,
        )

    def _insert_record(
        self,
        actor_id: int,
        action: str,
        entity_type: str,
        entity_id: str,
        before_json: str | None,
        after_json: str | None,
        ts: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (
                    user_id,
                    action,
                    entity_type,
                    entity_id,
                    before_json,
                    after_json,
                    ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (actor_id, action, entity_type, entity_id, before_json, after_json, ts),
            )
            conn.commit()

    def _fetch_entries(
        self,
        limit: int,
        user_id: int | None,
    ) -> tuple[AuditEntry, ...]:
        limit = max(1, min(50, limit))
        query = (
            "SELECT id, user_id, action, entity_type, entity_id, before_json, after_json, ts "
            "FROM audit_log"
        )
        args: list[object] = []
        if user_id is not None:
            query += " WHERE user_id = ?"
            args.append(user_id)
        query += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._connect() as conn:
            cur = conn.execute(query, tuple(args))
            rows = cur.fetchall()
        return tuple(self._row_to_entry(row) for row in rows)

    def _fetch_entry(self, op_id: int) -> AuditEntry | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT id, user_id, action, entity_type, entity_id, before_json, after_json, ts "
                "FROM audit_log WHERE id = ?",
                (op_id,),
            )
            row = cur.fetchone()
        return self._row_to_entry(row) if row else None

    def _row_to_entry(self, row: sqlite3.Row) -> AuditEntry:
        before = json.loads(row["before_json"]) if row["before_json"] else {}
        after = json.loads(row["after_json"]) if row["after_json"] else {}
        return AuditEntry(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            action=str(row["action"]),
            entity_type=str(row["entity_type"]),
            entity_id=str(row["entity_id"]),
            before=before,
            after=after,
            ts=datetime.fromisoformat(str(row["ts"])),
        )

    def _undo_result(self, entry: AuditEntry) -> bool:
        with self._connect() as conn:
            if entry.action == "create":
                cur = conn.execute(
                    "DELETE FROM results WHERE id = ?",
                    (int(entry.entity_id),),
                )
                conn.commit()
                return cur.rowcount > 0
            if entry.action == "update":
                if not entry.before:
                    return False
                cur = conn.execute(
                    """
                    UPDATE results
                    SET athlete_id = ?, athlete_name = ?, stroke = ?, distance = ?,
                        total_seconds = ?, timestamp = ?, is_pr = ?
                    WHERE id = ?
                    """,
                    (
                        entry.before["athlete_id"],
                        entry.before.get("athlete_name", ""),
                        entry.before["stroke"],
                        entry.before["distance"],
                        entry.before["total_seconds"],
                        entry.before["timestamp"],
                        int(bool(entry.before.get("is_pr", 0))),
                        int(entry.entity_id),
                    ),
                )
                conn.commit()
                return cur.rowcount > 0
            if entry.action == "delete":
                if not entry.before:
                    return False
                conn.execute(
                    """
                    INSERT OR REPLACE INTO results (
                        id, athlete_id, athlete_name, stroke, distance,
                        total_seconds, timestamp, is_pr
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(entry.entity_id),
                        entry.before["athlete_id"],
                        entry.before.get("athlete_name", ""),
                        entry.before["stroke"],
                        entry.before["distance"],
                        entry.before["total_seconds"],
                        entry.before["timestamp"],
                        int(bool(entry.before.get("is_pr", 0))),
                    ),
                )
                conn.commit()
                return True
        return False

    def _undo_template(self, entry: AuditEntry) -> bool:
        if entry.action == "create":
            return self._remove_template(entry.entity_id)
        if entry.action == "update":
            if not entry.before:
                return False
            return self._upsert_template(entry.before)
        if entry.action == "delete":
            if not entry.before:
                return False
            return self._upsert_template(entry.before)
        return False

    def _load_templates(self) -> list[dict[str, Any]]:
        if not self._template_path.exists():
            return []
        text = self._template_path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        data = json.loads(text)
        if isinstance(data, list):
            return [dict(item) for item in data]
        return []

    def _save_templates(self, items: Sequence[Mapping[str, Any]]) -> None:
        payload = [dict(item) for item in items]
        self._template_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _remove_template(self, template_id: str) -> bool:
        items = self._load_templates()
        new_items = [item for item in items if str(item.get("template_id")) != template_id]
        if len(new_items) == len(items):
            return False
        self._save_templates(new_items)
        return True

    def _upsert_template(self, payload: Mapping[str, Any]) -> bool:
        template_id = str(payload.get("template_id"))
        items = self._load_templates()
        replaced = False
        for index, item in enumerate(items):
            if str(item.get("template_id")) == template_id:
                items[index] = dict(payload)
                replaced = True
                break
        if not replaced:
            items.append(dict(payload))
        self._save_templates(items)
        return True


__all__ = [
    "ActionType",
    "AuditEntry",
    "AuditService",
    "EntityType",
]
