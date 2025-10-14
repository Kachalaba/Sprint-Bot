"""Fake Telegram sender implementing the notification port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sprint_bot.application.ports.services import NotificationService
from sprint_bot.domain.models import Athlete


@dataclass
class TelegramMessage:
    """Recorded Telegram markdown message."""

    chat_id: int
    text: str


@dataclass
class TrainingBroadcast:
    """Recorded broadcast payload for coaches."""

    coach: str
    athletes: tuple[Athlete, ...]


class TelegramSenderFake(NotificationService):
    """Collects outgoing Telegram interactions for assertions."""

    def __init__(self) -> None:
        self._messages: list[TelegramMessage] = []
        self._broadcasts: list[TrainingBroadcast] = []

    @property
    def messages(self) -> Sequence[TelegramMessage]:
        """Return recorded markdown messages in FIFO order."""

        return tuple(self._messages)

    @property
    def broadcasts(self) -> Sequence[TrainingBroadcast]:
        """Return recorded training broadcasts."""

        return tuple(self._broadcasts)

    async def send_markdown(self, chat_id: int, text: str) -> None:
        self._messages.append(TelegramMessage(chat_id=chat_id, text=text))

    async def broadcast_training_update(
        self, coach: str, athletes: Sequence[Athlete]
    ) -> None:
        self._broadcasts.append(
            TrainingBroadcast(coach=coach, athletes=tuple(athletes))
        )

    def drain_messages(self) -> tuple[TelegramMessage, ...]:
        """Return and clear collected messages."""

        drained = tuple(self._messages)
        self._messages.clear()
        return drained

    def drain_broadcasts(self) -> tuple[TrainingBroadcast, ...]:
        """Return and clear collected broadcasts."""

        drained = tuple(self._broadcasts)
        self._broadcasts.clear()
        return drained
