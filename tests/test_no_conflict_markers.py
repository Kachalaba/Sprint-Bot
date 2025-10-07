"""Regression tests ensuring no unresolved merge conflict markers remain."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFLICT_MARKERS = ("<" * 7, "=" * 7, ">" * 7)
IGNORED_DIR_NAMES = {
    ".git",
    "logs",
    "data",
    "reports",
    "examples",
}
IGNORED_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".mp3",
    ".mp4",
    ".pdf",
    ".zip",
    ".gz",
    ".xz",
    ".bz2",
    ".sqlite",
    ".db",
    ".log",
    ".pyc",
}


def _iter_project_files() -> list[Path]:
    files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(PROJECT_ROOT)
        if any(part in {"__pycache__", *IGNORED_DIR_NAMES} for part in relative.parts):
            continue
        if path.suffix.lower() in IGNORED_SUFFIXES:
            continue
        files.append(path)
    return files


@pytest.mark.parametrize(
    "file_path",
    _iter_project_files(),
    ids=lambda p: str(p.relative_to(PROJECT_ROOT)),
)
def test_repository_has_no_conflict_markers(file_path: Path) -> None:
    """Ensure that no file still contains unresolved merge conflict markers."""

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    assert not any(marker in content for marker in CONFLICT_MARKERS), (
        "Found unresolved merge conflict markers in"
        f" {file_path.relative_to(PROJECT_ROOT)}"
    )
