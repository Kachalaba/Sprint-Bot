from __future__ import annotations

import asyncio
from aiogram.types import BotCommand

from bot import (
    SUPPORTED_LANGUAGES,
    _DEFAULT_LANGUAGE,
    configure_bot_commands,
    get_bot_command_translations,
    get_help_message,
    get_start_message,
    get_unknown_command_message,
)


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, list[BotCommand]]] = []

    async def set_my_commands(
        self, commands: list[BotCommand], *, language_code: str | None = None
    ) -> None:
        self.calls.append((language_code, commands))


def test_start_message_translates_between_languages() -> None:
    uk_text = get_start_message(lang="uk")
    ru_text = get_start_message(lang="ru")
    assert uk_text == "Привіт! Це Sprint Bot. Скористайся меню, щоб почати роботу."
    assert ru_text == "Привет! Это Sprint Bot. Используйте меню, чтобы начать работу."
    assert uk_text != ru_text


def test_help_message_translates_between_languages() -> None:
    uk_text = get_help_message(lang="uk")
    ru_text = get_help_message(lang="ru")
    assert uk_text.splitlines()[0] == "Доступні команди:"
    assert ru_text.splitlines()[0] == "Доступные команды:"
    assert uk_text != ru_text


def test_unknown_command_message_translates_between_languages() -> None:
    uk_text = get_unknown_command_message(lang="uk")
    ru_text = get_unknown_command_message(lang="ru")
    assert uk_text == "Команду не розпізнано. Будь ласка, скористайтеся меню."
    assert ru_text == "Команда не распознана. Пожалуйста, воспользуйтесь меню."
    assert uk_text != ru_text


def test_configure_bot_commands_sets_translated_descriptions() -> None:
    fake_bot = FakeBot()

    asyncio.run(configure_bot_commands(fake_bot))

    assert any(language is None for language, _ in fake_bot.calls)

    localized_languages = {
        language for language, _ in fake_bot.calls if language is not None
    }
    expected_languages = set(SUPPORTED_LANGUAGES) - {_DEFAULT_LANGUAGE}
    assert localized_languages == expected_languages

    for language, commands in fake_bot.calls:
        descriptions = {cmd.command: cmd.description for cmd in commands}
        expected = get_bot_command_translations(
            lang=_DEFAULT_LANGUAGE if language is None else language
        )
        assert descriptions == expected
