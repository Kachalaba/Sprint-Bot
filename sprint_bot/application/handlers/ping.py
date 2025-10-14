"""Healthcheck handler exposing storage statistics via Telegram."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from sprint_bot.application.ports.storage import Storage

router = Router(name="sprint_bot_ping")


@router.message(Command("ping"))
async def handle_ping(message: Message, storage: Storage) -> None:
    """Respond with aggregated storage snapshot to validate data access."""

    athletes = await storage.athletes.list_active()
    races = await storage.results.list_recent(limit=1)
    if races:
        race = races[0]
        split_count = len(race.splits)
        pace = "n/a"
        if race.official_time and race.distance_meters:
            pace = f"{race.official_time.total_seconds() / race.distance_meters:.2f}s/m"
        text = (
            "PONG · "
            f"athletes={len(athletes)} · "
            f"last_race={race.name} · "
            f"splits={split_count} · "
            f"pace={pace}"
        )
    else:
        text = f"PONG · athletes={len(athletes)} · last_race=none"
    await message.answer(text)
