import asyncio
from pathlib import Path

import pytest

from i18n import reset_context_language, set_context_language, t
from services.io_service import IOService


@pytest.mark.parametrize("language", ["uk", "ru"])
def test_dry_run_issues_are_localized(tmp_path: Path, language: str) -> None:
    async def scenario() -> None:
        token = set_context_language(language)
        try:
            db_path = tmp_path / "results.db"
            service = IOService(db_path)
            await service.init()

            csv_content = (
                "athlete_id,stroke,distance,time,timestamp,is_pr\n"
                ",freestyle,100,1:10.00,2024-03-01T08:00:00,1\n"
                "102,,100,1:11.00,2024-03-01T08:05:00,0\n"
            )

            preview = await service.dry_run_import(csv_content.encode("utf-8"))

            assert preview.total_rows == 2
            messages = {issue.message for issue in preview.issues}
            assert messages == {
                t("expimp.errors.athlete_required", lang=language),
                t("expimp.errors.stroke_required", lang=language),
            }
        finally:
            reset_context_language(token)

    asyncio.run(scenario())
