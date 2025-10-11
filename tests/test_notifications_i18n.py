"""Tests for localized notification content generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pytest

from i18n import t
from notifications import NotificationService, SprintReminderPlan
from sprint_bot.domain.analytics import avg_speed
from utils import fmt_time


@dataclass
class DummyBot:
    """Stub bot to satisfy NotificationService dependencies in tests."""

    async def send_message(self, *args, **kwargs):  # pragma: no cover - defensive
        raise AssertionError("send_message should not be called during tests")


@pytest.fixture()
def notification_service() -> NotificationService:
    """Return notification service with stub bot and deterministic plan."""

    plan = SprintReminderPlan(weekdays=(0,), time_of_day=time(hour=9, minute=0))
    return NotificationService(bot=DummyBot(), sprint_plan=plan)


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_pr_summary_translated(
    notification_service: NotificationService, lang: str
) -> None:
    """Ensure PR summary message respects language selection."""

    new_prs = [(0, 15.0), (1, 16.0)]
    sob_delta = 0.75
    sob_current = 64.25
    summary = (
        notification_service._build_pr_summary(  # pylint: disable=protected-access
            athlete_name="Test Athlete",
            stroke="freestyle",
            dist=100,
            total=65.5,
            new_total_pr=True,
            total_pr_delta=1.5,
            new_prs=new_prs,
            has_segment_pr=True,
            segment_flags=[True, False, True, False],
            sob_delta=sob_delta,
            sob_current=sob_current,
            lang=lang,
        )
    )

    delta_suffix = notification_service._format_total_pr_delta(1.5)
    segment_items = ", ".join(
        t("note.pr_segment", lang=lang, seg=index + 1, time=fmt_time(value))
        for index, value in new_prs
    )
    expected_lines = [
        t("note.pr_title", lang=lang),
        t(
            "note.pr_athlete",
            lang=lang,
            athlete="Test Athlete",
            stroke="freestyle",
            distance=100,
        ),
        t("note.pr_total", lang=lang, time=fmt_time(65.5), delta=delta_suffix),
        t("note.pr_segments", lang=lang, items=segment_items),
        t(
            "note.sob_delta",
            lang=lang,
            delta=f"{sob_delta:.2f}",
            current=notification_service._format_sob_suffix(sob_current, lang=lang),
        ),
    ]

    assert summary == "\n".join(expected_lines)


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_broadcast_message_translated(
    notification_service: NotificationService, lang: str
) -> None:
    """Ensure broadcast message uses locale specific templates."""

    new_prs = [(0, 15.0), (1, 16.0)]
    sob_delta = 0.75
    sob_current = 64.25
    timestamp = "2024-01-01 10:00"
    message = notification_service._build_broadcast_message(  # pylint: disable=protected-access
        athlete_name="Test Athlete",
        stroke="freestyle",
        dist=100,
        total=65.5,
        timestamp=timestamp,
        actor_name="Coach",
        new_total_pr=True,
        total_pr_delta=1.5,
        new_prs=new_prs,
        sob_delta=sob_delta,
        sob_current=sob_current,
        lang=lang,
    )

    delta_suffix = notification_service._format_total_pr_delta(1.5)
    segment_items = ", ".join(
        t("note.pr_segment", lang=lang, seg=index + 1, time=fmt_time(value))
        for index, value in new_prs
    )
    expected_lines = [
        t("note.result_header", lang=lang),
        t(
            "note.result_body",
            lang=lang,
            athlete="Test Athlete",
            stroke="freestyle",
            distance=100,
            time=fmt_time(65.5),
        ),
        t(
            "note.result_speed",
            lang=lang,
            speed=f"{avg_speed([65.5], 100.0):.2f}",
        ),
        t(
            "note.result_added",
            lang=lang,
            timestamp=timestamp,
            coach="Coach",
        ),
        t("note.result_total_pr", lang=lang, delta=delta_suffix),
        t("note.result_segment_prs", lang=lang, items=segment_items),
        t(
            "note.result_sob",
            lang=lang,
            delta=f"{sob_delta:.2f}",
            current=notification_service._format_sob_suffix(sob_current, lang=lang),
        ),
    ]

    assert message == "\n".join(expected_lines)


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_service_notices_translated(
    notification_service: NotificationService, lang: str
) -> None:
    """Ensure service notifications reuse translation catalog."""

    assert notification_service.quiet_hours_notice(lang=lang) == t(
        "note.quiet_hours", lang=lang
    )
    assert notification_service.info_notice(lang=lang) == t(
        "note.info",
        lang=lang,
        quiet_window=t("note.info_quiet_disabled", lang=lang),
        local_time="—",
        quiet_state="—",
        subscription=t("note.info_subscription_always", lang=lang),
    )
