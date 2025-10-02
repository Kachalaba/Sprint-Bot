from __future__ import annotations

from datetime import datetime

import pytest

from handlers.export_import import _format_preview
from i18n import reset_context_language, set_context_language, t
from services.io_service import ImportIssue, ImportPreview, ImportRecord


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_dry_run_preview_messages_localized(lang: str) -> None:
    preview = ImportPreview(
        rows=(
            ImportRecord(
                row_number=2,
                athlete_id=101,
                athlete_name="Tester",
                stroke="freestyle",
                distance=50,
                total_seconds=25.3,
                timestamp=datetime(2024, 1, 1),
                is_pr=False,
            ),
        ),
        issues=(ImportIssue(row_number=3, message="custom error"),),
        total_rows=2,
    )

    token = set_context_language(lang)
    try:
        preview_text = _format_preview(preview)
    finally:
        reset_context_language(token)

    expected_fragments = [
        t("expimp.dry_run.title", lang=lang),
        t("expimp.dry_run.status.errors", lang=lang, count=1),
        t("expimp.dry_run.total", lang=lang, count=2),
        t("expimp.dry_run.ready", lang=lang, count=1),
        t("expimp.dry_run.invalid", lang=lang, count=1),
        t("expimp.dry_run.issues_title", lang=lang),
        t("expimp.dry_run.issue_line", lang=lang, row=3, reason="custom error"),
        t("expimp.import.confirm_question", lang=lang),
    ]

    for fragment in expected_fragments:
        assert fragment in preview_text
