"""Google Sheets backed implementation of the storage facade."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

import gspread
from gspread import Worksheet

from sprint_bot.application.ports.repositories import (
    AthletesRepo,
    CoachesRepo,
    RecordsRepo,
    ResultsRepo,
)
from sprint_bot.application.ports.storage import Storage
from sprint_bot.domain.models import Athlete, Coach, Race, SegmentPR, SoB, Split

logger = logging.getLogger(__name__)


def _normalise_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower())


def _parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"", "none", "na"}:
        return default
    if text in {"1", "true", "yes", "y", "active"}:
        return True
    if text in {"0", "false", "no", "n", "inactive"}:
        return False
    return default


def _parse_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_duration(value: Any) -> Optional[timedelta]:
    if value in (None, ""):
        return None
    if isinstance(value, timedelta):
        return value
    text = str(value).strip().lower()
    if text.endswith("s") and text[:-1].replace(".", "", 1).isdigit():
        try:
            return timedelta(seconds=float(text[:-1]))
        except ValueError:
            return None
    parts = re.split(r"[:\-]", text)
    try:
        parts = [float(part) for part in parts]
    except ValueError:
        return None
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)
    if len(parts) == 2:
        minutes, seconds = parts
        return timedelta(minutes=minutes, seconds=seconds)
    if len(parts) == 1:
        return timedelta(seconds=parts[0])
    return None


def _get_first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


async def _get_records(worksheet: Worksheet) -> list[dict[str, Any]]:
    return await asyncio.to_thread(worksheet.get_all_records)


async def _get_values(worksheet: Worksheet) -> list[list[Any]]:
    return await asyncio.to_thread(worksheet.get_all_values)


@dataclass(slots=True)
class SheetsOptions:
    """Configuration for Google Sheets storage."""

    spreadsheet_key: str
    credentials_path: Path


class GoogleSheetsStorage(Storage):
    """Storage facade backed by Google Sheets worksheets."""

    def __init__(self, *, spreadsheet_key: str, credentials_path: Path) -> None:
        self._options = SheetsOptions(spreadsheet_key=spreadsheet_key, credentials_path=credentials_path)
        self._client: gspread.Client | None = None
        self._spreadsheet: gspread.Spreadsheet | None = None
        self._athletes_repo = SheetsAthletesRepo(self)
        self._coaches_repo = SheetsCoachesRepo(self)
        self._results_repo = SheetsResultsRepo(self)
        self._records_repo = SheetsRecordsRepo(self)

    async def init(self) -> None:
        await asyncio.to_thread(self._connect)

    async def close(self) -> None:
        self._client = None
        self._spreadsheet = None

    @property
    def athletes(self) -> AthletesRepo:
        return self._athletes_repo

    @property
    def coaches(self) -> CoachesRepo:
        return self._coaches_repo

    @property
    def results(self) -> ResultsRepo:
        return self._results_repo

    @property
    def records(self) -> RecordsRepo:
        return self._records_repo

    def _connect(self) -> None:
        try:
            self._client = gspread.service_account(filename=str(self._options.credentials_path))
        except Exception as exc:  # pragma: no cover - depends on external creds
            raise RuntimeError(
                f"Unable to create Google Sheets client using credentials at {self._options.credentials_path}."
            ) from exc
        try:
            self._spreadsheet = self._client.open_by_key(self._options.spreadsheet_key)
        except gspread.SpreadsheetNotFound as exc:  # pragma: no cover - runtime validation
            raise RuntimeError(
                f"Spreadsheet with key '{self._options.spreadsheet_key}' not found or not shared with the service account."
            ) from exc

    def _require_spreadsheet(self) -> gspread.Spreadsheet:
        if self._spreadsheet is None:
            raise RuntimeError("Storage not initialised; call init() before usage.")
        return self._spreadsheet

    async def get_worksheet(self, name: str) -> Worksheet:
        spreadsheet = self._require_spreadsheet()
        try:
            return await asyncio.to_thread(spreadsheet.worksheet, name)
        except gspread.WorksheetNotFound as exc:
            logger.warning("Worksheet '%s' is missing in spreadsheet %s", name, spreadsheet.id)
            raise

    async def fetch_records(self, worksheet_name: str) -> list[dict[str, Any]]:
        try:
            worksheet = await self.get_worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            return []
        records = await _get_records(worksheet)
        normalised: list[dict[str, Any]] = []
        for record in records:
            normalised.append({_normalise_key(key): value for key, value in record.items()})
        return normalised

    async def fetch_values(self, worksheet_name: str) -> list[list[Any]]:
        try:
            worksheet = await self.get_worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            return []
        return await _get_values(worksheet)


class SheetsAthletesRepo(AthletesRepo):
    """Read-only athlete repository backed by a worksheet."""

    _worksheet_name = "AthletesList"

    def __init__(self, storage: GoogleSheetsStorage) -> None:
        self._storage = storage

    async def get(self, athlete_id: str) -> Optional[Athlete]:
        candidates = await self._load()
        for row in candidates:
            identifier = str(_get_first(row, "id", "athlete_id", "uid") or "").strip()
            if identifier and identifier == str(athlete_id):
                return self._row_to_entity(row)
        return None

    async def get_by_telegram(self, telegram_id: int) -> Optional[Athlete]:
        candidates = await self._load()
        for row in candidates:
            tele_id = _parse_int(_get_first(row, "telegram_id", "tg_id", "telegram"))
            if tele_id is not None and tele_id == telegram_id:
                return self._row_to_entity(row)
        return None

    async def list_active(self) -> Sequence[Athlete]:
        return tuple(
            athlete
            for athlete in map(self._row_to_entity, await self._load())
            if athlete is not None and athlete.is_active
        )

    async def list_by_coach(self, coach_id: str) -> Sequence[Athlete]:
        coach_id = str(coach_id)
        athletes = []
        for row in await self._load():
            coach_value = _get_first(row, "coach_id", "coach")
            if coach_value and str(coach_value).strip() == coach_id:
                entity = self._row_to_entity(row)
                if entity:
                    athletes.append(entity)
        return tuple(athletes)

    async def upsert(self, athlete: Athlete) -> Athlete:
        raise NotImplementedError("GoogleSheetsStorage is read-only in the new storage layer.")

    async def _load(self) -> Sequence[dict[str, Any]]:
        return await self._storage.fetch_records(self._worksheet_name)

    def _row_to_entity(self, row: Mapping[str, Any]) -> Optional[Athlete]:
        identifier = _get_first(row, "id", "athlete_id", "uid", "telegram_id")
        if identifier is None:
            logger.debug("Skipping athlete row without identifier: %s", row)
            return None
        athlete_id = str(identifier)
        full_name = str(_get_first(row, "full_name", "name", "athlete_name") or "").strip() or athlete_id
        telegram_id = _parse_int(_get_first(row, "telegram_id", "tg_id"))
        team_id = _get_first(row, "team_id", "team")
        coach_id = str(_get_first(row, "coach_id", "coach") or "").strip() or None
        date_of_birth = _parse_date(_get_first(row, "date_of_birth", "dob"))
        email = _get_first(row, "email")
        is_active = _parse_bool(_get_first(row, "is_active", "active", "status"), True)
        pr_5k = _parse_float(_get_first(row, "pr_5k_seconds", "pr_5k"))
        pr_10k = _parse_float(_get_first(row, "pr_10k_seconds", "pr_10k"))
        notes = _get_first(row, "notes", "comment")

        return Athlete(
            id=athlete_id,
            full_name=full_name,
            telegram_id=telegram_id,
            team_id=str(team_id) if team_id else None,
            coach_id=coach_id,
            date_of_birth=date_of_birth,
            email=str(email) if email else None,
            is_active=is_active,
            pr_5k_seconds=pr_5k,
            pr_10k_seconds=pr_10k,
            notes=str(notes) if notes else None,
        )


class SheetsCoachesRepo(CoachesRepo):
    """Read-only coach repository."""

    _worksheet_name = "Coaches"

    def __init__(self, storage: GoogleSheetsStorage) -> None:
        self._storage = storage

    async def get(self, coach_id: str) -> Optional[Coach]:
        for row in await self._load():
            identifier = str(_get_first(row, "id", "coach_id", "uid") or "").strip()
            if identifier and identifier == str(coach_id):
                return self._row_to_entity(row)
        return None

    async def get_by_telegram(self, telegram_id: int) -> Optional[Coach]:
        for row in await self._load():
            tele_id = _parse_int(_get_first(row, "telegram_id", "tg_id"))
            if tele_id is not None and tele_id == telegram_id:
                return self._row_to_entity(row)
        return None

    async def list_active(self) -> Sequence[Coach]:
        return tuple(
            coach
            for coach in map(self._row_to_entity, await self._load())
            if coach is not None and coach.is_active
        )

    async def upsert(self, coach: Coach) -> Coach:
        raise NotImplementedError("GoogleSheetsStorage is read-only in the new storage layer.")

    async def _load(self) -> Sequence[dict[str, Any]]:
        return await self._storage.fetch_records(self._worksheet_name)

    def _row_to_entity(self, row: Mapping[str, Any]) -> Optional[Coach]:
        identifier = _get_first(row, "id", "coach_id", "uid")
        if identifier is None:
            return None
        full_name = str(_get_first(row, "full_name", "name") or "").strip() or str(identifier)
        telegram_id = _parse_int(_get_first(row, "telegram_id", "tg_id"))
        email = _get_first(row, "email")
        phone = _get_first(row, "phone", "phone_number")
        is_active = _parse_bool(_get_first(row, "is_active", "active", "status"), True)
        return Coach(
            id=str(identifier),
            full_name=full_name,
            telegram_id=telegram_id,
            email=str(email) if email else None,
            phone=str(phone) if phone else None,
            is_active=is_active,
        )


class SheetsResultsRepo(ResultsRepo):
    """Result repository backed by the ``results`` worksheet."""

    _worksheet_name = "results"

    def __init__(self, storage: GoogleSheetsStorage) -> None:
        self._storage = storage

    async def get(self, race_id: str) -> Optional[Race]:
        for race in await self.list_recent(limit=10000):
            if race.id == str(race_id):
                return race
        return None

    async def list_by_athlete(self, athlete_id: str) -> Sequence[Race]:
        return tuple(
            race for race in await self.list_recent(limit=10000) if race.athlete_id == str(athlete_id)
        )

    async def list_recent(self, limit: int = 20) -> Sequence[Race]:
        rows = await self._storage.fetch_records(self._worksheet_name)
        races: list[Race] = []
        for row in rows:
            race = self._row_to_entity(row)
            if race:
                races.append(race)
        races.sort(key=lambda item: item.event_date, reverse=True)
        return tuple(races[:limit]) if limit else tuple(races)

    async def save(self, race: Race) -> Race:
        raise NotImplementedError("GoogleSheetsStorage is read-only in the new storage layer.")

    def _row_to_entity(self, row: Mapping[str, Any]) -> Optional[Race]:
        identifier = _get_first(row, "id", "race_id", "result_id")
        athlete_id = _get_first(row, "athlete_id", "athlete")
        event_date = _parse_date(_get_first(row, "event_date", "date"))
        name = str(_get_first(row, "name", "race", "event") or "").strip()
        if not identifier or not athlete_id or not event_date:
            logger.debug("Skipping malformed race row: %s", row)
            return None
        location = _get_first(row, "location", "place")
        distance = _parse_float(_get_first(row, "distance_meters", "distance", "distance_m")) or 0.0
        official_time = _parse_duration(_get_first(row, "official_time", "time", "total_time"))
        coach_id = str(_get_first(row, "coach_id", "coach") or "").strip() or None
        placement_overall = _parse_int(_get_first(row, "placement_overall", "place_overall"))
        placement_age = _parse_int(_get_first(row, "placement_age_group", "place_age"))
        splits = tuple(self._extract_splits(row))
        return Race(
            id=str(identifier),
            athlete_id=str(athlete_id),
            name=name or f"Race {identifier}",
            event_date=event_date,
            location=str(location) if location else None,
            distance_meters=distance,
            splits=splits,
            coach_id=coach_id,
            official_time=official_time,
            placement_overall=placement_overall,
            placement_age_group=placement_age,
        )

    def _extract_splits(self, row: Mapping[str, Any]) -> Iterable[Split]:
        grouped: dict[int, dict[str, Any]] = {}
        for key, value in row.items():
            if not isinstance(key, str):
                continue
            match = re.match(r"split[_\s-]?(\d+)[_\s-]?(.*)", key.lower())
            if not match:
                continue
            order = int(match.group(1))
            suffix = match.group(2) or "time"
            bucket = grouped.setdefault(order, {})
            bucket[suffix] = value
        for order, data in sorted(grouped.items()):
            segment_id = str(data.get("segment_id") or order)
            distance = _parse_float(data.get("distance") or data.get("distance_m")) or 0.0
            elapsed = _parse_duration(data.get("time") or data.get("elapsed") or data.get("duration"))
            recorded_at = _parse_datetime(data.get("recorded_at") or data.get("timestamp"))
            heart_rate = _parse_int(data.get("heart_rate") or data.get("hr"))
            cadence = _parse_int(data.get("cadence"))
            if elapsed is None:
                continue
            yield Split(
                segment_id=segment_id,
                order=order,
                distance_meters=distance,
                elapsed=elapsed,
                recorded_at=recorded_at,
                heart_rate=heart_rate,
                cadence=cadence,
            )


class SheetsRecordsRepo(RecordsRepo):
    """Personal records and SoB data sourced from worksheets."""

    _pr_worksheet = "pr"
    _sob_worksheet = "sob"

    def __init__(self, storage: GoogleSheetsStorage) -> None:
        self._storage = storage

    async def list_segment_prs(self, athlete_id: str) -> Sequence[SegmentPR]:
        prs: list[SegmentPR] = []
        for row in await self._storage.fetch_records(self._pr_worksheet):
            if str(_get_first(row, "athlete_id", "athlete") or "") != str(athlete_id):
                continue
            segment_id = str(_get_first(row, "segment_id", "segment") or "")
            if not segment_id:
                continue
            best_time = _parse_duration(_get_first(row, "best_time", "time"))
            achieved_at = _parse_datetime(_get_first(row, "achieved_at", "date")) or datetime.utcnow()
            race_id = _get_first(row, "race_id", "result_id")
            if best_time is None:
                continue
            prs.append(
                SegmentPR(
                    athlete_id=str(athlete_id),
                    segment_id=segment_id,
                    best_time=best_time,
                    achieved_at=achieved_at,
                    race_id=str(race_id) if race_id else None,
                )
            )
        return tuple(prs)

    async def upsert_segment_pr(self, record: SegmentPR) -> SegmentPR:
        raise NotImplementedError("GoogleSheetsStorage is read-only in the new storage layer.")

    async def get_sob(self, athlete_id: str) -> Optional[SoB]:
        for row in await self._storage.fetch_records(self._sob_worksheet):
            if str(_get_first(row, "athlete_id", "athlete") or "") != str(athlete_id):
                continue
            total_time = _parse_duration(_get_first(row, "total_time", "sob"))
            generated_at = _parse_datetime(_get_first(row, "generated_at", "updated_at")) or datetime.utcnow()
            if total_time is None:
                continue
            segments = await self.list_segment_prs(athlete_id)
            return SoB(
                athlete_id=str(athlete_id),
                total_time=total_time,
                segments=segments,
                generated_at=generated_at,
            )
        return None

    async def save_sob(self, sob: SoB) -> SoB:
        raise NotImplementedError("GoogleSheetsStorage is read-only in the new storage layer.")
