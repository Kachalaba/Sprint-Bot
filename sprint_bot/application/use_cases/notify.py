"""Notify use case: broadcast plain-text messages to subscribers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass(frozen=True, slots=True)
class BroadcastRequest:
    """Inbound payload describing a broadcast to subscribers."""

    text: str
    extra_recipients: tuple[int, ...] = ()


class NotificationGateway(Protocol):
    """Subset of ``NotificationService`` consumed by the use case."""

    async def broadcast_text(
        self, text: str, *, extra_recipients: Iterable[int] = ()
    ) -> None: ...
    async def subscribe(self, chat_id: int) -> bool: ...
    async def unsubscribe(self, chat_id: int) -> bool: ...
    async def is_subscribed(self, chat_id: int) -> bool: ...


class NotifyUseCase:
    """Coordinate subscription state and broadcast operations."""

    def __init__(self, *, gateway: NotificationGateway) -> None:
        self._gateway = gateway

    async def broadcast(self, request: BroadcastRequest) -> None:
        text = request.text.strip()
        if not text:
            raise ValueError("broadcast text must not be empty")
        await self._gateway.broadcast_text(
            text, extra_recipients=request.extra_recipients
        )

    async def subscribe(self, chat_id: int) -> bool:
        if chat_id == 0:
            raise ValueError("chat_id must be non-zero")
        return await self._gateway.subscribe(chat_id)

    async def unsubscribe(self, chat_id: int) -> bool:
        if chat_id == 0:
            raise ValueError("chat_id must be non-zero")
        return await self._gateway.unsubscribe(chat_id)

    async def is_subscribed(self, chat_id: int) -> bool:
        if chat_id == 0:
            raise ValueError("chat_id must be non-zero")
        return await self._gateway.is_subscribed(chat_id)


__all__ = [
    "BroadcastRequest",
    "NotificationGateway",
    "NotifyUseCase",
]
