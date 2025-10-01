"""Service access facade with lazy initialisation."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any

_BASE_MODULE: ModuleType | None = None


def _load_base() -> ModuleType:
    global _BASE_MODULE
    if _BASE_MODULE is None:
        _BASE_MODULE = import_module(".base", __name__)
    return _BASE_MODULE


def __getattr__(name: str) -> Any:
    base = _load_base()
    return getattr(base, name)


def __dir__() -> list[str]:
    base = _load_base()
    return sorted(set(globals().keys()) | set(dir(base)))
