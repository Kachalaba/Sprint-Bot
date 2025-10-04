import pytest

import i18n
from i18n import t

TURN_KEYS = [
    "add.step.turns",
    "add.summary",
    "turn.entry.title",
    "turn.entry.button",
    "turn.analysis.button",
    "turn.analysis.efficiency",
    "turn.recommendation.button",
    "turn.recommendation.breaststroke",
    "turn.recommendation.butterfly",
]


@pytest.mark.parametrize("key", TURN_KEYS)
def test_turn_translation_keys_present(key: str) -> None:
    for lang in ("uk", "ru"):
        assert key in i18n._LOCALE_DATA[lang]


def test_turn_entry_translations() -> None:
    ru_template = i18n._LOCALE_DATA["ru"]["turn.entry.button"]
    uk_template = i18n._LOCALE_DATA["uk"]["turn.entry.button"]
    assert t("turn.entry.button", lang="ru", number=2) == ru_template.format(number=2)
    assert t("turn.entry.button", lang="uk", number=2) == uk_template.format(number=2)


def test_turn_summary_translation_formatting() -> None:
    ru_template = i18n._LOCALE_DATA["ru"]["add.summary"]
    uk_template = i18n._LOCALE_DATA["uk"]["add.summary"]
    expected_args = dict(
        style="breaststroke",
        distance=100,
        segments="25m + turn",
        splits="0:30 0:31",
        turns="--",
        total="1:02.00",
    )
    expected_ru = ru_template.replace("\\n", "\n").format(**expected_args)
    assert t("add.summary", lang="ru", **expected_args) == expected_ru

    uk_args = dict(
        style="bat",
        distance=100,
        segments="25m + turn",
        splits="0:30 0:31",
        turns="--",
        total="1:02.00",
    )
    expected_uk = uk_template.replace("\\n", "\n").format(**uk_args)
    assert t("add.summary", lang="uk", **uk_args) == expected_uk


def test_turn_recommendation_translations() -> None:
    assert (
        t("turn.recommendation.breaststroke", lang="ru")
        == i18n._LOCALE_DATA["ru"]["turn.recommendation.breaststroke"]
    )
    assert (
        t("turn.recommendation.butterfly", lang="uk")
        == i18n._LOCALE_DATA["uk"]["turn.recommendation.butterfly"]
    )
