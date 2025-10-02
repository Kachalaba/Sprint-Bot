from __future__ import annotations

import pytest

from i18n import reset_context_language, set_context_language, t


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("ru", "Язык изменён."),
        ("uk", "Мову змінено."),
    ],
)
def test_user_language_changed_text(language: str, expected: str) -> None:
    token = set_context_language(language)
    try:
        assert t("user.language_changed") == expected
    finally:
        reset_context_language(token)
