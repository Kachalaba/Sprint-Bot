from i18n import t


def test_returns_translation_for_ukrainian_locale() -> None:
    assert t("menu.add_result", lang="uk") == "Додати результат"


def test_placeholder_substitution() -> None:
    assert t("menu.start", lang="ru", name="Никита") == "Привет, Никита!"
