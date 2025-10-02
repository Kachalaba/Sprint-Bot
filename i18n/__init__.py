"""Utilities for application internationalization."""

from __future__ import annotations

from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any, Dict, Tuple

_LOCALE_DATA: Dict[str, Dict[str, str]] = {}
_LANGUAGE_CONTEXT: ContextVar[str] = ContextVar("language", default="uk")


def _strip_quotes(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _parse_simple_yaml(content: str) -> Dict[str, Any]:
    """Parse a limited subset of YAML used for locale files."""
    root: Dict[str, Any] = {}
    stack: list[Tuple[int, Dict[str, Any]]] = [(-1, root)]

    for raw_line in content.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            raise ValueError(f"Invalid line in translation file: {raw_line!r}")

        key_part, value_part = line.split(":", 1)
        key = key_part.strip()
        value = value_part.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if value == "":
            nested: Dict[str, Any] = {}
            parent[key] = nested
            stack.append((indent, nested))
            continue

        parent[key] = _strip_quotes(value)

    return root


def _flatten_mapping(data: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
    """Flatten nested dictionaries into dot-separated keys."""
    flattened: Dict[str, str] = {}
    for key, value in data.items():
        composite_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(_flatten_mapping(value, composite_key))
        else:
            flattened[composite_key] = str(value)
    return flattened


def _load_translations() -> Dict[str, Dict[str, str]]:
    """Load translations from YAML files placed in the package directory."""
    package_dir = Path(__file__).resolve().parent
    translations: Dict[str, Dict[str, str]] = {}

    for path in package_dir.glob("*.yaml"):
        language_code = path.stem
        content = path.read_text(encoding="utf-8")
        parsed = _parse_simple_yaml(content)
        translations[language_code] = _flatten_mapping(parsed)
    return translations


_LOCALE_DATA = _load_translations()


def set_context_language(lang: str) -> Token[str]:
    """Push language value to the context stack."""

    return _LANGUAGE_CONTEXT.set(lang)


def reset_context_language(token: Token[str]) -> None:
    """Restore language context from token."""

    _LANGUAGE_CONTEXT.reset(token)


def get_current_language() -> str:
    """Return language stored in the current execution context."""

    return _LANGUAGE_CONTEXT.get()


def t(key: str, *, lang: str | None = None, **kwargs: Any) -> str:
    """Return a translated string for the provided key and language code."""

    language = lang or get_current_language()
    try:
        template = _LOCALE_DATA[language][key]
    except KeyError as exc:  # pragma: no cover - defensive branch
        raise KeyError(f"Missing translation for '{key}' in '{language}'") from exc

    if kwargs:
        return template.format(**kwargs)
    return template


__all__ = ["t", "get_current_language", "set_context_language", "reset_context_language"]
