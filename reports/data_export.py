"""Dataset preparation and serialisation for sprint exports."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Sequence

from openpyxl import Workbook

from utils import fmt_time

__all__ = [
    "ExportFilters",
    "ResultRecord",
    "build_cache_key",
    "export_results",
    "load_results",
]

_DEFAULT_DB_PATH = Path("data/results.db")


@dataclass(frozen=True, slots=True)
class ExportFilters:
    """User-provided filters for export commands."""

    athlete_id: int | None = None
    stroke: str | None = None
    distance: int | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True, slots=True)
class ResultRecord:
    """Single sprint attempt stored in SQLite."""

    result_id: int
    athlete_id: int
    athlete_name: str
    stroke: str
    distance: int
    total_seconds: float
    timestamp: datetime
    is_pr: bool
    segments: tuple[float, ...]

    @property
    def total_formatted(self) -> str:
        """Return formatted time for human-friendly exports."""

        return fmt_time(self.total_seconds)

    @property
    def segments_json(self) -> str:
        """Serialise segments as JSON."""

        return json.dumps(self.segments)


async def load_results(
    filters: ExportFilters,
    *,
    db_path: Path | str = _DEFAULT_DB_PATH,
) -> tuple[ResultRecord, ...]:
    """Load sprint results matching filters from SQLite."""

    path = Path(db_path)
    return await asyncio.to_thread(_load_results_sync, filters, path)


def _load_results_sync(
    filters: ExportFilters, db_path: Path
) -> tuple[ResultRecord, ...]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        results = _query_results(conn, filters)
        mapped = []
        for row in results:
            segments = _query_segments(conn, row["id"])
            mapped.append(
                ResultRecord(
                    result_id=int(row["id"]),
                    athlete_id=int(row["athlete_id"]),
                    athlete_name=str(row["athlete_name"] or ""),
                    stroke=str(row["stroke"]),
                    distance=int(row["distance"]),
                    total_seconds=float(row["total_seconds"]),
                    timestamp=_parse_timestamp(row["timestamp"]),
                    is_pr=bool(row["is_pr"]),
                    segments=segments,
                )
            )
        return tuple(mapped)


def _query_results(
    conn: sqlite3.Connection,
    filters: ExportFilters,
) -> Sequence[sqlite3.Row]:
    clauses = ["WHERE 1 = 1"]
    args: list[object] = []
    if filters.athlete_id is not None:
        clauses.append("AND athlete_id = ?")
        args.append(int(filters.athlete_id))
    if filters.stroke:
        clauses.append("AND stroke = ?")
        args.append(filters.stroke.strip().lower())
    if filters.distance is not None:
        clauses.append("AND distance = ?")
        args.append(int(filters.distance))
    if filters.date_from:
        clauses.append("AND DATE(timestamp) >= DATE(?)")
        args.append(filters.date_from.isoformat())
    if filters.date_to:
        clauses.append("AND DATE(timestamp) <= DATE(?)")
        args.append(filters.date_to.isoformat())
    where_clause = " ".join(clauses)
    query = (
        "SELECT id, athlete_id, athlete_name, "
        "stroke, distance, total_seconds, "
        "timestamp, is_pr FROM results {where} "
        "ORDER BY timestamp ASC, id ASC"
    ).format(where=where_clause)
    cursor = conn.execute(query, args)
    return cursor.fetchall()


def _query_segments(
    conn: sqlite3.Connection,
    result_id: int,
) -> tuple[float, ...]:
    try:
        rows = conn.execute(
            """
            SELECT segment_index, split_seconds
            FROM result_segments
            WHERE result_id = ?
            ORDER BY segment_index
            """,
            (result_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return ()
    splits = [float(row["split_seconds"]) for row in rows]
    return tuple(splits)


def _parse_timestamp(value: str | bytes | None) -> datetime:
    if isinstance(value, bytes):
        text = value.decode("utf-8")
    else:
        text = str(value or "")
    text = text.strip()
    if not text:
        raise ValueError("timestamp column cannot be empty")
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:  # pragma: no cover - corrupted data
        raise ValueError(f"Invalid timestamp format: {text!r}") from exc


async def export_results(
    filters: ExportFilters,
    fmt: str,
    *,
    db_path: Path | str = _DEFAULT_DB_PATH,
) -> bytes:
    """Serialise results into CSV or XLSX format."""

    records = await load_results(filters, db_path=db_path)
    fmt_lower = fmt.strip().lower()
    if fmt_lower == "csv":
        return await asyncio.to_thread(_records_to_csv, records)
    if fmt_lower in {"xlsx", "excel"}:
        return await asyncio.to_thread(_records_to_xlsx, records)
    raise ValueError(f"Unsupported export format: {fmt}")


def _records_to_csv(records: Iterable[ResultRecord]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "timestamp",
            "athlete_id",
            "athlete_name",
            "stroke",
            "distance",
            "total_seconds",
            "total_formatted",
            "is_pr",
            "segments_json",
        ]
    )
    for record in records:
        writer.writerow(
            [
                record.timestamp.isoformat(),
                record.athlete_id,
                record.athlete_name,
                record.stroke,
                record.distance,
                f"{record.total_seconds:.3f}",
                record.total_formatted,
                int(record.is_pr),
                record.segments_json,
            ]
        )
    return buffer.getvalue().encode("utf-8")


def _records_to_xlsx(records: Iterable[ResultRecord]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "results"
    headers = [
        "timestamp",
        "athlete_id",
        "athlete_name",
        "stroke",
        "distance",
        "total_seconds",
        "total_formatted",
        "is_pr",
        "segments_json",
    ]
    sheet.append(headers)
    for record in records:
        sheet.append(
            [
                record.timestamp.isoformat(),
                record.athlete_id,
                record.athlete_name,
                record.stroke,
                record.distance,
                float(f"{record.total_seconds:.3f}"),
                record.total_formatted,
                int(record.is_pr),
                record.segments_json,
            ]
        )
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def build_cache_key(
    filters: ExportFilters,
    *,
    fmt: str,
    namespace: str,
    db_path: Path | str = _DEFAULT_DB_PATH,
) -> str:
    """Build deterministic cache key for given parameters."""

    payload = {
        **asdict(filters),
        "fmt": fmt.strip().lower(),
        "db_path": str(Path(db_path).resolve()),
        "namespace": namespace,
    }
    return json.dumps(payload, sort_keys=True)
