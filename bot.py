from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Dispatcher

from handlers.common import router as common_router
from handlers.sprint_actions import router as sprint_router
from services import bot

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
LOG_FILE = "logs/bot.log"
handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(handler)
logging.basicConfig(level=logging.WARNING)


def setup_dispatcher() -> Dispatcher:
    """Configure dispatcher with routers."""
    dp = Dispatcher()
    dp.include_router(common_router)
    dp.include_router(sprint_router)
    return dp


async def main() -> None:
    """Start Sprint Bot."""
    logger.info("[SprintBot] starting…")
    dp = setup_dispatcher()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
