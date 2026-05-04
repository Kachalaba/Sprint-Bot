"""Composition root for the Sprint Bot Telegram application."""

from .container import Container
from .main import run, setup_dispatcher

__all__ = ["Container", "run", "setup_dispatcher"]
