"""Utilities for searching stored sprint results."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True, slots=True)
class SearchFilters:
    """Query parameters supplied by the search wizard."""

    athlete_id: int | None = None
    stroke: str | None = None
    distance: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    only_pr: bool = False


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Single sprint result matched by the query."""

    result_id: int
    athlete_id: int
    athlete_name: str
    stroke: str
    distance: int
    total_seconds: float
    timestamp: datetime
    is_pr: bool


@dataclass(frozen=True, slots=True)
class SearchPage:
    """Paginated collection of search results."""

    items: tuple[SearchResult, ...]
    total: int
    page: int
    pages: int


class QueryService:
    """Read sprint results with flexible filters."""

    def __init__(self, db_path: Path | str = Path("data/results.db")) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        """Ensure SQLite schema exists."""

        async with self._lock:
            await asyncio.to_thread(self._ensure_schema)

    async def search_results(
        self,
        filters: SearchFilters,
        *,
        page: int = 1,
        page_size: int = 5,
    ) -> SearchPage:
        """Return paginated results for provided filters."""

        if page_size <= 0:
            raise ValueError("page_size must be positive")
        if page <= 0:
            page = 1
        base_sql, args = self._build_where_clause(filters)
        total = await asyncio.to_thread(self._count_results, base_sql, args)
        if total == 0:
            return SearchPage(items=(), total=0, page=1, pages=0)
        pages = (total + page_size - 1) // page_size
        if page > pages:
            page = pages
        offset = (page - 1) * page_size
        rows = await asyncio.to_thread(
            self._fetch_rows, base_sql, args, page_size, offset
        )
        return SearchPage(items=tuple(rows), total=total, page=page, pages=pages)

    # --- internal helpers -------------------------------------------------

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
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
                CREATE INDEX IF NOT EXISTS idx_results_timestamp
                    ON results(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_results_athlete
                    ON results(athlete_id);
                CREATE INDEX IF NOT EXISTS idx_results_stroke
                    ON results(stroke);
                CREATE INDEX IF NOT EXISTS idx_results_distance
                    ON results(distance);
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _build_where_clause(
        filters: SearchFilters,
    ) -> tuple[str, tuple[object, ...]]:
        clauses = ["FROM results WHERE 1 = 1"]
        args: list[object] = []
        if filters.athlete_id is not None:
            clauses.append("AND athlete_id = ?")
            args.append(filters.athlete_id)
        if filters.stroke:
            clauses.append("AND stroke = ?")
            args.append(filters.stroke)
        if filters.distance is not None:
            clauses.append("AND distance = ?")
            args.append(filters.distance)
        if filters.date_from:
            clauses.append("AND DATE(timestamp) >= DATE(?)")
            args.append(filters.date_from.isoformat())
        if filters.date_to:
            clauses.append("AND DATE(timestamp) <= DATE(?)")
            args.append(filters.date_to.isoformat())
        if filters.only_pr:
            clauses.append("AND is_pr = 1")
        sql = " ".join(clauses)
        return sql, tuple(args)

    def _count_results(self, base_sql: str, args: Sequence[object]) -> int:
        query = f"SELECT COUNT(*) {base_sql}"
        with self._connect() as conn:
            cur = conn.execute(query, args)
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def _fetch_rows(
        self,
        base_sql: str,
        args: Sequence[object],
        limit: int,
        offset: int,
    ) -> tuple[SearchResult, ...]:
        query = (
            "SELECT id, athlete_id, athlete_name, stroke, distance, "
            "total_seconds, timestamp, is_pr "
            f"{base_sql} ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?"
        )
        with self._connect() as conn:
            cur = conn.execute(query, (*args, limit, offset))
            rows = cur.fetchall()
        results: list[SearchResult] = []
        for row in rows:
            timestamp = self._parse_timestamp(row["timestamp"])
            results.append(
                SearchResult(
                    result_id=int(row["id"]),
                    athlete_id=int(row["athlete_id"]),
                    athlete_name=str(row["athlete_name"] or ""),
                    stroke=str(row["stroke"]),
                    distance=int(row["distance"]),
                    total_seconds=float(row["total_seconds"]),
                    timestamp=timestamp,
                    is_pr=bool(row["is_pr"]),
                )
            )
        return tuple(results)

    @staticmethod
    def _parse_timestamp(value: str | bytes | None) -> datetime:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        text = (value or "").strip()
        if not text:
            raise ValueError("timestamp column cannot be empty")
        try:
            return datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid timestamp format: {text!r}") from exc


__all__ = [
    "QueryService",
    "SearchFilters",
    "SearchPage",
    "SearchResult",
]
