from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from middlewares.throttling import ThrottlingMiddleware


@dataclass
class _User:
    id: int


@dataclass
class _Message:
    from_user: _User | None
    answer: AsyncMock | None = None


@dataclass
class _Callback:
    from_user: _User | None
    answer: AsyncMock | None = None
    data: str = "noop"


@pytest.mark.asyncio
async def test_passes_event_when_within_quota() -> None:
    fake_time = [0.0]
    middleware = ThrottlingMiddleware(
        capacity=2, refill_per_second=1, clock=lambda: fake_time[0]
    )
    handler = AsyncMock(return_value="OK")
    event = _Message(from_user=_User(id=42), answer=AsyncMock())

    result = await middleware(handler, event, {})

    assert result == "OK"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_rejects_excessive_burst() -> None:
    fake_time = [0.0]
    middleware = ThrottlingMiddleware(
        capacity=2, refill_per_second=1, clock=lambda: fake_time[0]
    )
    handler = AsyncMock(return_value="OK")
    user = _User(id=42)

    msgs = [
        _Message(from_user=user, answer=AsyncMock()) for _ in range(4)
    ]
    results = []
    for msg in msgs:
        results.append(await middleware(handler, msg, {}))

    assert results.count("OK") == 2
    assert results.count(None) == 2


@pytest.mark.asyncio
async def test_recovers_after_refill() -> None:
    fake_time = [0.0]
    middleware = ThrottlingMiddleware(
        capacity=1, refill_per_second=1, clock=lambda: fake_time[0]
    )
    handler = AsyncMock(return_value="OK")
    user = _User(id=42)

    assert await middleware(handler, _Message(user, AsyncMock()), {}) == "OK"
    assert await middleware(handler, _Message(user, AsyncMock()), {}) is None

    fake_time[0] = 1.5
    assert await middleware(handler, _Message(user, AsyncMock()), {}) == "OK"


@pytest.mark.asyncio
async def test_separate_users_have_independent_buckets() -> None:
    middleware = ThrottlingMiddleware(capacity=1, refill_per_second=0.001)
    handler = AsyncMock(return_value="OK")

    user_a = _User(id=1)
    user_b = _User(id=2)

    assert await middleware(handler, _Message(user_a, AsyncMock()), {}) == "OK"
    assert await middleware(handler, _Message(user_b, AsyncMock()), {}) == "OK"


@pytest.mark.asyncio
async def test_no_user_event_passes_through() -> None:
    middleware = ThrottlingMiddleware(capacity=1, refill_per_second=0.001)
    handler = AsyncMock(return_value="OK")

    event = _Message(from_user=None)
    assert await middleware(handler, event, {}) == "OK"


@pytest.mark.asyncio
async def test_callback_query_answer_called_when_throttled() -> None:
    fake_time = [0.0]
    middleware = ThrottlingMiddleware(
        capacity=1, refill_per_second=1, clock=lambda: fake_time[0]
    )
    handler = AsyncMock(return_value="OK")
    user = _User(id=7)
    cb_first = _Callback(from_user=user, answer=AsyncMock())
    cb_second = _Callback(from_user=user, answer=AsyncMock())

    assert await middleware(handler, cb_first, {}) == "OK"
    assert await middleware(handler, cb_second, {}) is None

    cb_second.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_message_notice_when_configured() -> None:
    fake_time = [0.0]
    middleware = ThrottlingMiddleware(
        capacity=1,
        refill_per_second=1,
        notice="Slow down",
        clock=lambda: fake_time[0],
    )
    handler = AsyncMock(return_value="OK")
    user = _User(id=7)
    first = _Message(user, AsyncMock())
    second = _Message(user, AsyncMock())

    assert await middleware(handler, first, {}) == "OK"
    await middleware(handler, second, {})

    second.answer.assert_awaited_once_with("Slow down")


def test_invalid_capacity_rejected() -> None:
    with pytest.raises(ValueError, match="capacity"):
        ThrottlingMiddleware(capacity=0)
    with pytest.raises(ValueError, match="refill"):
        ThrottlingMiddleware(refill_per_second=0)
