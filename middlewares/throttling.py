"""Per-user throttling middleware using a token bucket algorithm.

Telegram bot users can flood handlers with rapid taps and commands; this
middleware enforces a per-user rate so the bot stays responsive and does
not get throttled by Telegram. Buckets are scoped by Telegram user id so
distinct users don't interfere with each other.

The middleware silently drops events that exceed the rate. When the
underlying event is a ``CallbackQuery`` we still answer it so the
spinning indicator on the client clears; for ``Message`` updates we
optionally send a localised "too fast" reply (configurable).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from utils.logger import get_logger

logger = get_logger(__name__)

Handler = Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]]


class _TokenBucket:
    """Allow ``capacity`` events per ``capacity / refill_per_second`` window."""

    __slots__ = ("capacity", "tokens", "refill_per_second", "last_refill")

    def __init__(self, *, capacity: float, refill_per_second: float, now: float) -> None:
        self.capacity = capacity
        self.tokens = capacity
        self.refill_per_second = refill_per_second
        self.last_refill = now

    def try_consume(self, *, now: float, cost: float = 1.0) -> bool:
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.refill_per_second,
            )
            self.last_refill = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


class ThrottlingMiddleware(BaseMiddleware):
    """Reject updates that exceed a configured per-user rate."""

    DEFAULT_CAPACITY = 5.0
    DEFAULT_REFILL_PER_SECOND = 1.0

    def __init__(
        self,
        *,
        capacity: float = DEFAULT_CAPACITY,
        refill_per_second: float = DEFAULT_REFILL_PER_SECOND,
        notice: str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive")
        self._capacity = float(capacity)
        self._refill = float(refill_per_second)
        self._notice = notice
        self._clock = clock
        self._buckets: Dict[int, _TokenBucket] = {}
        self._lock = asyncio.Lock()

    async def __call__(
        self, handler: Handler, event: TelegramObject, data: Dict[str, Any]
    ) -> Any:
        user_id = self._extract_user_id(event)
        if user_id is None:
            return await handler(event, data)

        if not await self._consume(user_id):
            await self._handle_rate_limited(event, user_id)
            return None
        return await handler(event, data)

    async def _consume(self, user_id: int) -> bool:
        async with self._lock:
            now = self._clock()
            bucket = self._buckets.get(user_id)
            if bucket is None:
                bucket = _TokenBucket(
                    capacity=self._capacity,
                    refill_per_second=self._refill,
                    now=now,
                )
                self._buckets[user_id] = bucket
            return bucket.try_consume(now=now)

    async def _handle_rate_limited(
        self, event: TelegramObject, user_id: int
    ) -> None:
        logger.info(
            "throttled_event",
            extra={"user_id": user_id, "event": type(event).__name__},
        )
        try:
            if self._is_callback_query(event):
                await event.answer(self._notice or "Too fast — try again", show_alert=False)
            elif self._is_message(event) and self._notice:
                await event.answer(self._notice)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("throttle_notice_failed: %s", exc)

    @staticmethod
    def _is_callback_query(event: TelegramObject) -> bool:
        if isinstance(event, CallbackQuery):
            return True
        # Duck-typing fallback so tests can use lightweight stand-ins.
        return hasattr(event, "data") and hasattr(event, "answer") and not hasattr(event, "text")

    @staticmethod
    def _is_message(event: TelegramObject) -> bool:
        if isinstance(event, Message):
            return True
        return hasattr(event, "answer") and not hasattr(event, "data")

    @staticmethod
    def _extract_user_id(event: TelegramObject) -> Optional[int]:
        user = getattr(event, "from_user", None)
        if user is None:
            return None
        return getattr(user, "id", None)


__all__ = ["ThrottlingMiddleware"]
