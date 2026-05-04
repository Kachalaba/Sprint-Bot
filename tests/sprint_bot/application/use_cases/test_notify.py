from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from sprint_bot.application.use_cases import BroadcastRequest, NotifyUseCase


@pytest.mark.asyncio
async def test_broadcast_strips_text_and_passes_recipients() -> None:
    gateway = AsyncMock()
    gateway.broadcast_text = AsyncMock()

    use_case = NotifyUseCase(gateway=gateway)
    await use_case.broadcast(
        BroadcastRequest(text="  hello team  ", extra_recipients=(1, 2))
    )

    gateway.broadcast_text.assert_awaited_once_with(
        "hello team", extra_recipients=(1, 2)
    )


@pytest.mark.asyncio
async def test_broadcast_rejects_empty_text() -> None:
    use_case = NotifyUseCase(gateway=AsyncMock())
    with pytest.raises(ValueError, match="empty"):
        await use_case.broadcast(BroadcastRequest(text="   "))


@pytest.mark.asyncio
async def test_subscription_helpers() -> None:
    gateway = AsyncMock()
    gateway.subscribe = AsyncMock(return_value=True)
    gateway.unsubscribe = AsyncMock(return_value=True)
    gateway.is_subscribed = AsyncMock(return_value=False)

    use_case = NotifyUseCase(gateway=gateway)
    assert await use_case.subscribe(7) is True
    assert await use_case.unsubscribe(7) is True
    assert await use_case.is_subscribed(7) is False


@pytest.mark.asyncio
async def test_subscription_validates_chat_id() -> None:
    use_case = NotifyUseCase(gateway=AsyncMock())
    with pytest.raises(ValueError, match="chat_id"):
        await use_case.subscribe(0)
    with pytest.raises(ValueError, match="chat_id"):
        await use_case.unsubscribe(0)
    with pytest.raises(ValueError, match="chat_id"):
        await use_case.is_subscribed(0)
