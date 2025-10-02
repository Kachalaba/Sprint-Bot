import asyncio
from dataclasses import dataclass, field
from typing import Any, List, Tuple

from handlers import error_handler
from i18n import t


@dataclass
class FakeMessage:
    texts: List[str] = field(default_factory=list)

    async def answer(self, text: str) -> None:
        self.texts.append(text)


@dataclass
class FakeCallbackQuery:
    alerts: List[Tuple[str, Any]] = field(default_factory=list)

    async def answer(self, text: str, show_alert: bool = False) -> None:
        self.alerts.append((text, show_alert))


@dataclass
class FakeUpdate:
    message: FakeMessage | None = None
    callback_query: FakeCallbackQuery | None = None


@dataclass
class FakeErrorEvent:
    exception: Exception
    update: FakeUpdate


def test_handle_timeout_error_uses_translation() -> None:
    message = FakeMessage()
    event = FakeErrorEvent(asyncio.TimeoutError(), FakeUpdate(message=message))

    asyncio.run(error_handler.handle_any_exception(event))  # type: ignore[arg-type]

    assert message.texts == [t("error.timeout")]


def test_handle_invalid_input_error_uses_translation() -> None:
    message = FakeMessage()
    event = FakeErrorEvent(ValueError("bad"), FakeUpdate(message=message))

    asyncio.run(error_handler.handle_any_exception(event))  # type: ignore[arg-type]

    assert message.texts == [t("error.invalid_input")]


def test_handle_forbidden_error_alerts_callback() -> None:
    callback = FakeCallbackQuery()
    event = FakeErrorEvent(
        PermissionError("denied"), FakeUpdate(callback_query=callback)
    )

    asyncio.run(error_handler.handle_any_exception(event))  # type: ignore[arg-type]

    assert callback.alerts == [(t("error.forbidden"), True)]


def test_handle_api_error_defaults_to_internal() -> None:
    message = FakeMessage()
    event = FakeErrorEvent(Exception("api"), FakeUpdate(message=message))

    asyncio.run(error_handler.handle_telegram_api_error(event))  # type: ignore[arg-type]

    assert message.texts == [t("error.internal")]
