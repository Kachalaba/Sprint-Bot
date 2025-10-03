"""Sentry integration helpers."""

from __future__ import annotations

import os
from typing import Final

try:  # pragma: no cover - exercised implicitly in environments without sentry_sdk
    import sentry_sdk  # type: ignore[import]
except ModuleNotFoundError:  # pragma: no cover - sentry optional in tests
    sentry_sdk = None  # type: ignore[assignment]

from utils.meta import BOT_VERSION

ENVIRONMENT: Final[str] = os.getenv("ENV", "development")
"""Deployment environment name used for Sentry tagging."""

_RELEASE: Final[str] = f"sprint-bot@{BOT_VERSION}"
_SENTRY_INITIALIZED = False


def init_sentry() -> bool:
    """Initialise Sentry SDK if ``SENTRY_DSN`` is configured."""

    global _SENTRY_INITIALIZED
    if _SENTRY_INITIALIZED:
        return True

    if sentry_sdk is None:
        return False

    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=ENVIRONMENT,
        release=_RELEASE,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("bot_version", BOT_VERSION)
    sentry_sdk.set_tag("environment", ENVIRONMENT)
    _SENTRY_INITIALIZED = True
    return True


def capture_exception(exc: BaseException, *, user_id: int | None = None) -> None:
    """Report ``exc`` to Sentry if the SDK was initialised."""

    if not _SENTRY_INITIALIZED or sentry_sdk is None:
        return

    with sentry_sdk.push_scope() as scope:
        scope.set_tag("bot_version", BOT_VERSION)
        scope.set_tag("environment", ENVIRONMENT)
        if user_id is not None:
            scope.set_user({"id": user_id})
        sentry_sdk.capture_exception(exc)
