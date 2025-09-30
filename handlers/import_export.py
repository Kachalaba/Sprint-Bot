"""Utilities for importing sprint results from spreadsheets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from services import ws_athletes

IMPORT_ERROR_TEXT = (
    "❗ Import failed. Please fix the highlighted issues and try again. "
    "Unknown athletes were found; ensure every row references a registered athlete "
    "from AthletesList."
)


@dataclass(frozen=True)
class ValidationIssue:
    """Single validation issue for an import row."""

    row_index: int
    message: str

    def format_for_report(self) -> str:
        """Return a human readable representation."""
        return f"Row {self.row_index}: {self.message}"


def _is_blank(value: Any) -> bool:
    """Return True if the provided value should be treated as empty."""

    if value is None:
        return True
    try:
        if isinstance(value, float) and value != value:  # NaN check
            return True
    except Exception:
        pass
    text = str(value).strip()
    return text == ""


def _normalise_athlete_id(value: Any) -> str:
    """Convert athlete identifiers to a comparable string form."""

    if _is_blank(value):
        return ""
    try:
        if isinstance(value, float) and value.is_integer():
            value = int(value)
    except AttributeError:
        pass
    return str(value).strip()


def _extract_optional_name(row: Any) -> str:
    """Extract an optional athlete name column from a dataframe row."""

    for key in ("athlete_name", "name", "Name", "full_name", "Full Name"):
        try:
            candidate = row.get(key)  # type: ignore[attr-defined]
        except AttributeError:
            candidate = None
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text:
            return text
    return ""


def _load_registered_athletes() -> dict[str, str]:
    """Fetch registered athletes from Google Sheets."""

    try:
        records = ws_athletes.get_all_records()
    except AttributeError:
        # Fallback to raw values if records are not available
        values = ws_athletes.get_all_values()  # type: ignore[attr-defined]
        if not values:
            return {}
        header, *rows = values
        id_idx = None
        name_idx = None
        for idx, title in enumerate(header):
            title_lower = str(title).strip().lower()
            if title_lower in {"id", "athlete_id", "athlete id"}:
                id_idx = idx
            elif title_lower in {"name", "athlete_name", "full name"}:
                name_idx = idx
        roster: dict[str, str] = {}
        if id_idx is None:
            return roster
        for row in rows:
            if id_idx >= len(row):
                continue
            raw_id = row[id_idx]
            athlete_id = _normalise_athlete_id(raw_id)
            if not athlete_id:
                continue
            athlete_name = ""
            if name_idx is not None and name_idx < len(row):
                athlete_name = str(row[name_idx]).strip()
            roster[athlete_id] = athlete_name
        return roster
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise RuntimeError("Failed to load registered athletes") from exc

    roster: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        athlete_id = _normalise_athlete_id(
            record.get("ID")
            or record.get("Id")
            or record.get("athlete_id")
            or record.get("AthleteID")
        )
        if not athlete_id:
            continue
        name_value = (
            record.get("Name")
            or record.get("Full Name")
            or record.get("athlete_name")
            or ""
        )
        roster[athlete_id] = str(name_value).strip()
    return roster


def _iter_rows(df: Any) -> Iterator[tuple[int, Any]]:
    """Yield rows from a dataframe-like object with one-based index."""

    try:
        iterator = df.iterrows()
    except AttributeError as exc:  # pragma: no cover - defensive
        raise TypeError("Object does not support iterrows()") from exc
    for excel_row, (_, row) in enumerate(iterator, start=2):
        yield excel_row, row


def _validate_dataframe(df: Any) -> list[ValidationIssue]:
    """Validate import dataframe contents.

    Ensures each row references a registered athlete. Returns a list of
    validation issues; empty list means the dataframe is valid.
    """

    try:
        columns = {str(col).strip().lower() for col in df.columns}
    except AttributeError:
        raise TypeError("DataFrame-like object must provide a 'columns' attribute")

    if "athlete_id" not in columns:
        raise ValueError("Import file must contain an 'athlete_id' column")

    roster = _load_registered_athletes()
    issues: list[ValidationIssue] = []

    for row_index, row in _iter_rows(df):
        raw_id = None
        try:
            raw_id = row.get("athlete_id")
        except AttributeError:
            try:
                raw_id = row["athlete_id"]  # type: ignore[index]
            except Exception:
                raw_id = None
        athlete_id = _normalise_athlete_id(raw_id)
        athlete_name = _extract_optional_name(row)

        if not athlete_id:
            issues.append(
                ValidationIssue(
                    row_index,
                    "athlete_id is empty. Only registered athletes can be imported.",
                )
            )
            continue

        registered_name = roster.get(athlete_id)
        if registered_name is None:
            if athlete_name:
                message = (
                    f"Unknown athlete {athlete_name} (ID {athlete_id}). "
                    "Only registered athletes can be imported."
                )
            else:
                message = (
                    f"Unknown athlete ID {athlete_id}. Only registered athletes "
                    "can be imported."
                )
            issues.append(ValidationIssue(row_index, message))
            continue

        if athlete_name and athlete_name.casefold() != registered_name.casefold():
            issues.append(
                ValidationIssue(
                    row_index,
                    (
                        f"Name '{athlete_name}' does not match registered name "
                        f"'{registered_name}' for athlete ID {athlete_id}."
                    ),
                )
            )

    return issues


__all__ = [
    "IMPORT_ERROR_TEXT",
    "ValidationIssue",
    "_validate_dataframe",
]
