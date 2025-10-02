"""Ensure template hint translations exist for supported locales."""

import pytest

from i18n import t


@pytest.mark.parametrize("lang", ["uk", "ru"])
@pytest.mark.parametrize("key", ["tpl.hint.50_free", "tpl.hint.100_free"])
def test_template_hint_translations_exist(lang: str, key: str) -> None:
    text = t(key, lang=lang)
    assert text, "Translation must not be empty"
    assert text != key, "Translation should resolve to localized text"
