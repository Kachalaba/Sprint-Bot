"""Ensure sprint stats summaries rely on localization."""

from __future__ import annotations

import html
import importlib
import sys
import types

import pytest

from i18n import reset_context_language, set_context_language, t
from utils import fmt_time


@pytest.fixture()
def format_result_summary(monkeypatch: pytest.MonkeyPatch):
    """Provide summary formatter with stubbed service dependencies."""

    services_stub = types.ModuleType("services")
    services_stub.__path__ = []  # mark as package for submodule imports

    empty_sheet = types.SimpleNamespace(
        get_all_values=lambda: [],
        append_row=lambda *args, **kwargs: None,
        update=lambda *args, **kwargs: None,
        cell=lambda *args, **kwargs: types.SimpleNamespace(value=""),
    )

    services_stub.get_athletes_worksheet = lambda: empty_sheet
    services_stub.get_log_worksheet = lambda: empty_sheet
    services_stub.get_pr_worksheet = lambda: empty_sheet
    services_stub.get_results_worksheet = lambda: empty_sheet
    monkeypatch.setitem(sys.modules, "services", services_stub)

    stats_stub = types.ModuleType("services.stats_service")

    class _SobStats:  # pragma: no cover - placeholder for type hints
        pass

    stats_stub.SobStats = _SobStats
    stats_stub.calc_segment_prs = lambda *args, **kwargs: []
    stats_stub.calc_sob = lambda *args, **kwargs: None
    stats_stub.calc_total_pr = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "services.stats_service", stats_stub)

    module = importlib.import_module("handlers.sprint_actions")
    try:
        yield module._format_result_summary
    finally:
        sys.modules.pop("handlers.sprint_actions", None)


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_result_summary_uses_translations(format_result_summary, lang: str) -> None:
    stats_payload = {
        "new_total_pr": True,
        "total_pr_delta": 1.23,
        "sob_delta": 0.5,
        "sob_current": 240.0,
    }
    new_segment_prs = [(0, 30.5)]
    comment = "Примітка & тест"

    token = set_context_language(lang)
    try:
        summary = format_result_summary(
            100,
            63.25,
            new_segment_prs,
            stats_payload,
            comment,
        )
    finally:
        reset_context_language(token)

    delta_value = stats_payload["total_pr_delta"]
    delta_suffix = f" (−{delta_value:.2f} с)" if delta_value else ""
    expected_total_pr = t("stats.total_pr", lang=lang, delta=delta_suffix)
    expected_segment_pr = t(
        "stats.segment_pr",
        lang=lang,
        index=1,
        time=fmt_time(new_segment_prs[0][1]),
    )
    current_suffix = t("note.sob_current", lang=lang, current=fmt_time(240.0))
    expected_sob = t(
        "stats.sob",
        lang=lang,
        delta=f"{stats_payload['sob_delta']:.2f}",
        current=current_suffix,
    )
    expected_comment = t(
        "stats.comment",
        lang=lang,
        comment=html.escape(comment),
    )

    for fragment in (
        expected_total_pr,
        expected_segment_pr,
        expected_sob,
        expected_comment,
    ):
        assert fragment in summary
