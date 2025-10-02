import importlib
import sys
import types

import pytest

from i18n import reset_context_language, set_context_language, t


def _load_reports_module(monkeypatch: pytest.MonkeyPatch):
    fake_services = types.ModuleType("services")
    fake_services.ws_pr = types.SimpleNamespace(get_all_values=lambda: [])
    fake_services.ws_results = types.SimpleNamespace(get_all_values=lambda: [])
    monkeypatch.setitem(sys.modules, "services", fake_services)
    module_name = "handlers.reports"
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_report_messages_use_translations(
    monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    module = _load_reports_module(monkeypatch)
    token = set_context_language(lang)
    try:
        assert module.build_report_error("mention") == t("report.errors.mention")
        assert module.build_report_error("invalid_id") == t("report.errors.invalid_id")
        assert module.build_report_error("forbidden") == t("report.errors.forbidden")
        assert module.build_report_error("no_results") == t("report.errors.no_results")
        assert module.build_report_error("empty_report") == t(
            "report.errors.empty_report"
        )
        caption = module.build_report_caption(200, "freestyle")
        assert caption == t("report.caption.last", distance=200, stroke="freestyle")
    finally:
        reset_context_language(token)


def test_generate_image_report_uses_translations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("reports.image_report")

    mapping = {
        "report.title": "Title {stroke} {distance}",
        "report.col.segment": "Segment",
        "report.col.time": "Time",
        "report.col.ms": "Speed",
        "report.col.percent_best": "%",
        "report.chart.pace": "Pace",
        "report.footer.total": "Total",
        "report.footer.pr": "PR",
        "report.footer.sob": "SoB",
        "report.status.yes": "Yes",
        "report.status.no": "No",
    }
    used_keys: list[str] = []

    def fake_t(key: str, **kwargs) -> str:
        used_keys.append(key)
        template = mapping[key]
        if kwargs:
            return template.format(**kwargs)
        return template

    monkeypatch.setattr(module, "t", fake_t)

    payload = module.AttemptReport(
        athlete_name="Test",
        stroke="freestyle",
        distance=100,
        timestamp="2024-01-01T00:00:00",
        total_time=60.0,
        segments=[module.SegmentReportRow(time=30.0, distance=50.0, best=29.5)],
        total_is_pr=True,
        sob_improved=False,
    )

    result = module.generate_image_report(payload)

    assert isinstance(result, bytes)
    for key in mapping:
        assert key in used_keys
