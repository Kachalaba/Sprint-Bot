"""CSV import/export helpers for sprint results."""

from __future__ import annotations

import asyncio
import csv
import io
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from services.audit_service import AuditService

from utils import parse_time


CSV_HEADERS: tuple[str, ...] = (
    "athlete_id",
    "athlete_name",
    "stroke",
    "distance",
    "total_seconds",
    "timestamp",
    "is_pr",
)


@dataclass(frozen=True, slots=True)
class ImportIssue:
    """Describe a validation issue for an import row."""

    row_number: int
    message: str


@dataclass(frozen=True, slots=True)
class ImportRecord:
    """Validated import row ready to be inserted."""

    row_number: int
    athlete_id: int
    athlete_name: str
    stroke: str
    distance: int
    total_seconds: float
    timestamp: datetime
    is_pr: bool


@dataclass(frozen=True, slots=True)
class ImportPreview:
    """Result of a dry-run import attempt."""

    rows: tuple[ImportRecord, ...]
    issues: tuple[ImportIssue, ...]
    total_rows: int


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Summary of an applied import."""

    inserted: int
    skipped: int


class IOService:
    """Handle CSV based import/export of results."""

    _SETUP_SQL = """
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        athlete_id INTEGER NOT NULL,
        athlete_name TEXT NOT NULL DEFAULT '',
        stroke TEXT NOT NULL,
        distance INTEGER NOT NULL,
        total_seconds REAL NOT NULL,
        timestamp TEXT NOT NULL,
        is_pr INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_io_results_timestamp ON results(timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_io_results_athlete ON results(athlete_id);
    """

    def __init__(
        self,
        db_path: Path | str = Path("data/results.db"),
        audit_service: AuditService | None = None,
    ) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._audit = audit_service

    async def init(self) -> None:
        """Ensure SQLite schema exists."""

        async with self._lock:
            await asyncio.to_thread(self._ensure_schema)

    async def export_results(
        self, *, athlete_ids: Sequence[int] | None = None
    ) -> bytes:
        """Export results filtered by athletes as UTF-8 CSV bytes."""

        rows = await asyncio.to_thread(self._fetch_rows, tuple(athlete_ids) if athlete_ids else None)
        if not rows:
            return b""

        buffer = io.StringIO()
        buffer.write("\ufeff")
        writer = csv.DictWriter(buffer, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "athlete_id": row["athlete_id"],
                    "athlete_name": row["athlete_name"],
                    "stroke": row["stroke"],
                    "distance": row["distance"],
                    "total_seconds": row["total_seconds"],
                    "timestamp": row["timestamp"],
                    "is_pr": row["is_pr"],
                }
            )
        return buffer.getvalue().encode("utf-8")

    async def dry_run_import(self, content: bytes) -> ImportPreview:
        """Validate CSV file and return preview of rows to import."""

        return await asyncio.to_thread(self._dry_run_import, content)

    async def apply_import(
        self,
        preview: ImportPreview,
        *,
        user_id: int | None = None,
    ) -> ImportResult:
        """Insert validated rows from preview."""

        async with self._lock:
            inserted, skipped, created_rows = await asyncio.to_thread(
                self._insert_rows, preview.rows
            )
        if self._audit and user_id is not None and user_id > 0:
            for row in created_rows:
                await self._audit.log_result_create(actor_id=user_id, result=row)
        return ImportResult(inserted=inserted, skipped=skipped)

    # --- synchronous helpers -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(self._SETUP_SQL)
            conn.commit()

    def _fetch_rows(self, athlete_ids: Sequence[int] | None) -> tuple[sqlite3.Row, ...]:
        query = (
            "SELECT athlete_id, athlete_name, stroke, distance, total_seconds, timestamp, is_pr "
            "FROM results"
        )
        args: tuple[object, ...] = ()
        if athlete_ids:
            placeholders = ",".join("?" for _ in athlete_ids)
            query += f" WHERE athlete_id IN ({placeholders})"
            args = tuple(int(value) for value in athlete_ids)
        query += " ORDER BY timestamp DESC, id DESC"
        with self._connect() as conn:
            cursor = conn.execute(query, args)
            rows = cursor.fetchall()
        return tuple(rows)

    def _dry_run_import(self, content: bytes) -> ImportPreview:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        issues: list[ImportIssue] = []
        rows: list[ImportRecord] = []
        total = 0
        with self._connect() as conn:
            for index, raw_row in enumerate(reader, start=2):
                total += 1
                try:
                    record = self._validate_row(raw_row, index)
                except ValueError as exc:
                    issues.append(ImportIssue(row_number=index, message=str(exc)))
                    continue
                if self._record_exists(record, conn=conn):
                    issues.append(
                        ImportIssue(
                            row_number=index,
                            message="duplicate result already stored; skipping",
                        )
                    )
                    continue
                rows.append(record)
        return ImportPreview(rows=tuple(rows), issues=tuple(issues), total_rows=total)

    def _validate_row(self, row: dict[str, str], index: int) -> ImportRecord:
        athlete_raw = (row.get("athlete_id") or "").strip()
        if not athlete_raw:
            raise ValueError("athlete_id is required")
        try:
            athlete_id = int(float(athlete_raw))
        except ValueError as exc:
            raise ValueError(f"invalid athlete_id: {athlete_raw!r}") from exc
        if athlete_id <= 0:
            raise ValueError("athlete_id must be positive")

        stroke = (row.get("stroke") or "").strip()
        if not stroke:
            raise ValueError("stroke is required")

        distance_raw = (row.get("distance") or "").strip()
        if not distance_raw:
            raise ValueError("distance is required")
        try:
            distance = int(float(distance_raw))
        except ValueError as exc:
            raise ValueError(f"invalid distance: {distance_raw!r}") from exc
        if distance <= 0:
            raise ValueError("distance must be positive")

        time_raw = (row.get("time") or row.get("total_seconds") or "").strip()
        if not time_raw:
            raise ValueError("time column is required")
        try:
            total_seconds = parse_time(time_raw) if not _looks_like_number(time_raw) else float(time_raw)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if total_seconds <= 0:
            raise ValueError("time value must be positive")

        timestamp_raw = (row.get("timestamp") or row.get("date") or "").strip()
        if not timestamp_raw:
            raise ValueError("timestamp is required (ISO format)")
        try:
            timestamp = datetime.fromisoformat(timestamp_raw)
        except ValueError as exc:
            raise ValueError(f"invalid timestamp: {timestamp_raw!r}") from exc

        pr_raw = (row.get("is_pr") or row.get("pr") or "0").strip().lower()
        is_pr = pr_raw in {"1", "true", "yes", "y"}

        athlete_name = (row.get("athlete_name") or row.get("name") or "").strip()

        return ImportRecord(
            row_number=index,
            athlete_id=athlete_id,
            athlete_name=athlete_name,
            stroke=stroke,
            distance=distance,
            total_seconds=float(total_seconds),
            timestamp=timestamp,
            is_pr=is_pr,
        )

    def _record_exists(
        self, record: ImportRecord, *, conn: sqlite3.Connection | None = None
    ) -> bool:
        query = (
            "SELECT 1 FROM results WHERE athlete_id = ? AND stroke = ? AND distance = ? "
            "AND ABS(total_seconds - ?) < 1e-6 AND timestamp = ?"
        )
        args = (
            record.athlete_id,
            record.stroke,
            record.distance,
            record.total_seconds,
            record.timestamp.isoformat(),
        )
        if conn is None:
            with self._connect() as own_conn:
                cursor = own_conn.execute(query, args)
                return cursor.fetchone() is not None
        cursor = conn.execute(query, args)
        return cursor.fetchone() is not None

    def _insert_rows(
        self, rows: Iterable[ImportRecord]
    ) -> tuple[int, int, list[dict[str, object]]]:
        inserted = 0
        skipped = 0
        created: list[dict[str, object]] = []
        with self._connect() as conn:
            for record in rows:
                if self._record_exists(record, conn=conn):
                    skipped += 1
                    continue
                cursor = conn.execute(
                    """
                    INSERT INTO results (
                        athlete_id,
                        athlete_name,
                        stroke,
                        distance,
                        total_seconds,
                        timestamp,
                        is_pr
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.athlete_id,
                        record.athlete_name,
                        record.stroke,
                        record.distance,
                        record.total_seconds,
                        record.timestamp.isoformat(),
                        int(record.is_pr),
                    ),
                )
                row_id = int(cursor.lastrowid)
                created.append(
                    {
                        "id": row_id,
                        "athlete_id": record.athlete_id,
                        "athlete_name": record.athlete_name,
                        "stroke": record.stroke,
                        "distance": record.distance,
                        "total_seconds": record.total_seconds,
                        "timestamp": record.timestamp.isoformat(),
                        "is_pr": int(record.is_pr),
                    }
                )
                inserted += 1
            conn.commit()
        return inserted, skipped, created


def _looks_like_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


__all__ = [
    "CSV_HEADERS",
    "IOService",
    "ImportIssue",
    "ImportPreview",
    "ImportRecord",
    "ImportResult",
]
