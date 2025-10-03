"""Tests for localized role-based access messages."""

from i18n import reset_context_language, set_context_language
from role_service import ROLE_ADMIN, ROLE_TRAINER
from utils.roles import RequireRolesFilter, build_forbidden_message


def test_build_forbidden_message_ru() -> None:
    token = set_context_language("ru")
    try:
        message = build_forbidden_message([ROLE_ADMIN])
    finally:
        reset_context_language(token)

    assert message == (
        "У вас нет доступа к этому действию.\n" "Требуется роль: Администратор."
    )


def test_filter_forbidden_message_uk() -> None:
    token = set_context_language("uk")
    try:
        filt = RequireRolesFilter(ROLE_TRAINER, ROLE_ADMIN)
        message = filt.get_forbidden_message()
    finally:
        reset_context_language(token)

    assert message == (
        "У вас немає доступу до цієї дії.\n" "Потрібна роль: Тренер / Адміністратор."
    )
