from __future__ import annotations

from handlers.leaderboard import build_leaderboard_lines
from i18n import reset_context_language, set_context_language, t
from services.stats_service import LeaderboardEntry, StatsPeriod


def _sample_entries() -> tuple[LeaderboardEntry, LeaderboardEntry]:
    return (
        LeaderboardEntry(
            athlete_id=1,
            athlete_name="Ivan",
            pr_count=3,
            attempts=5,
        ),
        LeaderboardEntry(
            athlete_id=2,
            athlete_name="Olena",
            pr_count=2,
            attempts=4,
        ),
    )


def test_leaderboard_translations_ru() -> None:
    token = set_context_language("ru")
    try:
        lines = build_leaderboard_lines(_sample_entries(), StatsPeriod.WEEK)
    finally:
        reset_context_language(token)
    assert lines[0] == t("lead.title.week", lang="ru")
    assert lines[1] == t(
        "lead.item",
        place=1,
        user="Ivan",
        value=t("lead.value", pr=3, attempts=5, lang="ru"),
    )
    assert lines[2] == t(
        "lead.item",
        place=2,
        user="Olena",
        value=t("lead.value", pr=2, attempts=4, lang="ru"),
    )


def test_leaderboard_translations_uk() -> None:
    token = set_context_language("uk")
    try:
        lines = build_leaderboard_lines(_sample_entries(), StatsPeriod.MONTH)
    finally:
        reset_context_language(token)
    assert lines[0] == t("lead.title.month", lang="uk")
    assert lines[1] == t(
        "lead.item",
        place=1,
        user="Ivan",
        value=t("lead.value", pr=3, attempts=5, lang="uk"),
    )
    assert lines[2] == t(
        "lead.item",
        place=2,
        user="Olena",
        value=t("lead.value", pr=2, attempts=4, lang="uk"),
    )
