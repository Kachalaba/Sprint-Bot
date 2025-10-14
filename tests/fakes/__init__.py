"""In-memory fakes for external integrations used in tests."""

from .sheets import SheetsClientFake, WorksheetFake
from .telegram import TelegramSenderFake

__all__ = [
    "SheetsClientFake",
    "WorksheetFake",
    "TelegramSenderFake",
]
