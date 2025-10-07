import importlib
import sys
import types

import pytest

from i18n import reset_context_language, set_context_language, t
from utils import fmt_time


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_result_card_translates_between_languages(monkeypatch, lang: str) -> None:
    fake_services = types.ModuleType("services")

    def _empty_results_sheet():
        return types.SimpleNamespace(get_all_values=lambda: [])

    fake_services.get_pr_worksheet = _empty_results_sheet
    fake_services.get_results_worksheet = _empty_results_sheet
    monkeypatch.setitem(sys.modules, "services", fake_services)
    module = importlib.import_module("handlers.results")
    format_result_card = module.format_result_card
    token = set_context_language(lang)
    try:
        segments = [31.25, 32.5, 33.75]
        sob_value = sum(segments)
        card = format_result_card(
            "freestyle",
            100,
            date="2023-11-15",
            total=65.3,
            sob=sob_value,
            splits=segments,
        )
        expected_lines = [
            t("res.card.style", style="freestyle"),
            t("res.card.distance", distance=100),
            t("res.card.date", date="2023-11-15"),
            t("res.card.total", total=fmt_time(65.3)),
            t("res.card.sob", sob=fmt_time(sob_value)),
            t(
                "res.card.splits",
                splits=", ".join(fmt_time(value) for value in segments),
            ),
        ]
        assert card == "\n".join(expected_lines)
        assert t("res.saved")
        assert t("res.updated")
        assert t("res.deleted")
        assert t("res.card.title", name="Test", id=123)
    finally:
        reset_context_language(token)
