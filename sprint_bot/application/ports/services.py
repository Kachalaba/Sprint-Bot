"""Service contracts for infrastructure integrations."""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence

from sprint_bot.domain.models import Athlete, Race


class WorksheetService(Protocol):
    """Gateway for reading and mutating structured tabular data."""

    async def fetch_athlete_snapshot(self, athlete_id: str) -> Mapping[str, str]:
        """Return a normalized row for the athlete."""

    async def sync_race(self, race: Race) -> None:
        """Synchronise race data with the upstream worksheet."""

    async def list_pending_updates(self) -> Sequence[Mapping[str, str]]:
        """Return buffered worksheet mutations awaiting processing."""


class StorageService(Protocol):
    """Abstracts binary storage such as S3 buckets."""

    async def put_object(self, key: str, payload: bytes, *, content_type: str) -> str:
        """Store artefact and return public or signed URL."""

    async def get_object(self, key: str) -> bytes:
        """Retrieve object payload by key."""


class NotificationService(Protocol):
    """Dispatches outbound notifications through Telegram."""

    async def send_markdown(self, chat_id: int, text: str) -> None:
        """Send formatted message to a chat."""

    async def broadcast_training_update(self, coach: str, athletes: Sequence[Athlete]) -> None:
        """Notify a coach about athlete updates in bulk."""


class ObservabilityService(Protocol):
    """Captures diagnostics, metrics and error reports."""

    async def capture_exception(self, error: BaseException, context: Mapping[str, str]) -> None:
        """Send exception to the monitoring backend (Sentry)."""

    async def record_metric(self, name: str, value: float, *, tags: Mapping[str, str] | None = None) -> None:
        """Emit numeric metric for performance tracking."""
