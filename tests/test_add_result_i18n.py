import pytest

from handlers.add_result import build_quick_prompt, build_quick_saved
from i18n import reset_context_language, set_context_language, t
from sprint_bot.domain.analytics import avg_speed
from utils import fmt_time


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_quick_add_prompts_and_summary_i18n(lang: str) -> None:
    token = set_context_language(lang)
    try:
        prompt = build_quick_prompt(0, 25)
        expected_prompt = "\n".join(
            [t("add.quick.prompt", idx=1, distance="25"), t("add.quick.example")]
        )
        assert prompt == expected_prompt

        total = 65.12
        summary = build_quick_saved(100, total)
        expected_summary = t(
            "add.quick.saved",
            total=fmt_time(total),
            speed=f"{avg_speed([total], 100.0):.2f}",
        )
        assert summary == expected_summary

        assert t("error.invalid_time")
        assert t("error.splits_mismatch", diff="0:01.23")
    finally:
        reset_context_language(token)
