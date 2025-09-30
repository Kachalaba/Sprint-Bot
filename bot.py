from __future__ import annotations

import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

from aiogram import Dispatcher

from handlers.common import router as common_router
from handlers.error_handler import router as error_router
from handlers.progress import router as progress_router
from handlers.registration import router as registration_router
from handlers.sprint_actions import router as sprint_router
from services import bot

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.WARNING)
stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))

logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def setup_dispatcher() -> Dispatcher:
    """Configure dispatcher with routers."""
    dp = Dispatcher()
    dp.include_router(registration_router)
    dp.include_router(common_router)
    dp.include_router(progress_router)
    dp.include_router(sprint_router)
    dp.include_router(error_router)
    return dp


async def main() -> None:
    """Start Sprint Bot."""
    logger.info("[SprintBot] starting…")
    dp = setup_dispatcher()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
