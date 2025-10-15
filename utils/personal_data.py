"""Helpers for anonymising personal identifiers in logs and telemetry."""

from __future__ import annotations

import hashlib
from typing import Any

__all__ = [
    "mask_identifier",
    "mask_username",
    "scrub_sensitive_mapping",
]

_DIGEST_SIZE = 10
_SENSITIVE_KEYS = {"chat_id", "user_id", "username"}


def _stable_digest(value: str) -> str:
    normalised = value.strip().encode("utf-8", "ignore")
    return hashlib.blake2b(normalised, digest_size=_DIGEST_SIZE).hexdigest()


def mask_identifier(value: int | str, *, prefix: str = "id") -> str:
    """Return an anonymised representation of ``value`` suitable for logs."""

    raw = str(value)
    digest = _stable_digest(f"{prefix}:{raw}")
    return f"{prefix}-{digest[:6]}...{digest[-4:]}"


def mask_username(username: str) -> str:
    """Mask a Telegram username while keeping it traceable across events."""

    cleaned = username.lstrip("@").strip()
    if not cleaned:
        return "user-anon"
    digest = _stable_digest(f"username:{cleaned}")
    return f"user-{digest[:8]}"


def _scrub_value(value: Any, *, key: str | None = None) -> Any:
    if value is None:
        return None
    lowered = key.lower() if isinstance(key, str) else None

    if lowered in {"chat_id", "user_id"}:
        return mask_identifier(value, prefix=lowered.replace("_id", ""))
    if lowered == "username" and isinstance(value, str):
        return mask_username(value)

    if isinstance(value, dict):
        return scrub_sensitive_mapping(value)
    if isinstance(value, list):
        return [_scrub_value(item, key=key) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item, key=key) for item in value)
    return value


def scrub_sensitive_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask chat/user identifiers inside ``mapping`` in-place."""

    for key, value in list(mapping.items()):
        if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
            mapping[key] = _scrub_value(value, key=key)
        elif isinstance(value, (dict, list, tuple)):
            mapping[key] = _scrub_value(
                value, key=key if isinstance(key, str) else None
            )
    return mapping
