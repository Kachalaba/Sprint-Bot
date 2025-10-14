"""In-memory Google Sheets fake client for repository tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import gspread


@dataclass
class WorksheetFake:
    """Lightweight worksheet mimic supporting record/value reads."""

    records: list[Mapping[str, Any]] = field(default_factory=list)
    values: list[list[Any]] = field(default_factory=list)
    header: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.values and not self.header:
            self.header = [str(column) for column in self.values[0]]
        if not self.values and self.records:
            keys: set[str] = set()
            for record in self.records:
                keys.update(str(key) for key in record.keys())
            self.header = sorted(keys)
            self.values = [self.header[:]]
            for record in self.records:
                self.values.append([record.get(key, "") for key in self.header])
        elif self.values and not self.records and self.header:
            for row in self.values[1:]:
                self.records.append(dict(zip(self.header, row)))

    def get_all_records(self) -> list[dict[str, Any]]:
        """Return deep copy of worksheet records."""

        return [dict(record) for record in self.records]

    def get_all_values(self) -> list[list[Any]]:
        """Return tabular data with header row."""

        return [list(row) for row in self.values]

    def append_row(self, row: Iterable[Any]) -> None:
        """Append a new row updating internal state."""

        materialised = list(row)
        if not self.header:
            self.header = [f"col_{index}" for index in range(len(materialised))]
            if not self.values:
                self.values.append(self.header[:])
        elif not self.values:
            self.values.append(self.header[:])
        self.values.append(materialised)
        if self.header and len(materialised) == len(self.header):
            self.records.append(dict(zip(self.header, materialised)))


@dataclass
class SpreadsheetFake:
    """Collection of worksheets addressable by title."""

    worksheets: dict[str, WorksheetFake] = field(default_factory=dict)
    id: str = "fake-spreadsheet"
    title: str = "Fake Spreadsheet"

    def worksheet(self, title: str) -> WorksheetFake:
        try:
            return self.worksheets[title]
        except KeyError as exc:  # pragma: no cover - defensive
            raise gspread.WorksheetNotFound(title) from exc

    def add_worksheet(self, title: str, worksheet: WorksheetFake) -> None:
        self.worksheets[title] = worksheet


class SheetsClientFake:
    """Fake gspread client for unit and contract tests."""

    def __init__(self) -> None:
        self._storage: dict[str, SpreadsheetFake] = {}

    def register_spreadsheet(
        self,
        key: str,
        worksheets: (
            Mapping[str, WorksheetFake | Iterable[Mapping[str, Any]]] | None
        ) = None,
    ) -> None:
        """Register spreadsheet contents for a given key."""

        mapping: dict[str, WorksheetFake] = {}
        if worksheets:
            for name, worksheet in worksheets.items():
                mapping[name] = (
                    worksheet
                    if isinstance(worksheet, WorksheetFake)
                    else WorksheetFake(records=list(worksheet))
                )
        spreadsheet = SpreadsheetFake(worksheets=mapping, id=key, title=f"Spreadsheet {key}")
        self._storage[key] = spreadsheet

    def open_by_key(self, key: str) -> SpreadsheetFake:
        try:
            return self._storage[key]
        except KeyError as exc:  # pragma: no cover - defensive
            raise gspread.SpreadsheetNotFound(
                f"Spreadsheet {key} is not registered"
            ) from exc
