from __future__ import annotations

from handlers.onboarding import _format_profile
from i18n import reset_context_language, set_context_language, t
from role_service import ROLE_TRAINER
from services.user_service import UserProfile


def _collect_step_texts() -> list[str]:
    return [
        t("onb.choose_role"),
        t("onb.enter_name"),
        t("onb.group_hint"),
        t("onb.choose_lang"),
        t("common.done"),
    ]


def test_onboarding_texts_ru() -> None:
    token = set_context_language("ru")
    try:
        assert _collect_step_texts() == [
            "Привет! Давайте настроим ваш профиль. Выберите роль:",
            "Введите ваше имя и фамилию (2-64 символа, без спецсимволов).",
            "Укажите группу/клуб (опционально) или пропустите шаг:",
            "Выберите язык интерфейса:",
            "Готово!",
        ]
        profile = UserProfile(
            telegram_id=1,
            role=ROLE_TRAINER,
            full_name="Coach",
            group_name="Sharks",
            language="ru",
        )
        assert _format_profile(profile) == (
            "Ваш профиль готов!\n"
            "Роль: <b>Тренер</b>\n"
            "Имя: <b>Coach</b>\n"
            "Группа: <b>Sharks</b>\n"
            "Язык: <b>Русский</b>"
        )
    finally:
        reset_context_language(token)


def test_onboarding_texts_uk() -> None:
    token = set_context_language("uk")
    try:
        assert _collect_step_texts() == [
            "Привіт! Давайте налаштуємо ваш профіль. Оберіть роль:",
            "Введіть ваше ім'я та прізвище (2-64 символи, без спецсимволів).",
            "Укажіть групу/клуб (за бажанням) або пропустіть крок:",
            "Оберіть мову інтерфейсу:",
            "Готово!",
        ]
        profile = UserProfile(
            telegram_id=2,
            role=ROLE_TRAINER,
            full_name="Coach",
            group_name="Sharks",
            language="uk",
        )
        assert _format_profile(profile) == (
            "Ваш профіль готовий!\n"
            "Роль: <b>Тренер</b>\n"
            "Ім'я: <b>Coach</b>\n"
            "Група: <b>Sharks</b>\n"
            "Мова: <b>Українська</b>"
        )
    finally:
        reset_context_language(token)
