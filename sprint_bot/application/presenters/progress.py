"""Render weekly-progress views for delivery via Telegram messages."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Protocol, Sequence


class HighlightLike(Protocol):
    """Single highlighted attempt within a progress summary."""

    stroke: str
    distance: int
    total_seconds: float
    timestamp: datetime
    is_pr: bool


class WeeklyProgressLike(Protocol):
    """Aggregate of attempts and PR statistics for the last week."""

    attempts: int
    pr_count: int
    highlights: Sequence[HighlightLike]


class ProgressTranslator(Protocol):
    """Localisation callable abstracted away from concrete i18n backends."""

    def __call__(
        self, key: str, /, *, lang: str | None = None, **params: object
    ) -> str: ...


def _format_seconds(value: float) -> str:
    """Human-readable ``mm:ss.xx`` representation of a swim time."""

    minutes = int(value // 60)
    seconds = value - minutes * 60
    if minutes:
        return f"{minutes}:{seconds:05.2f}"
    return f"{seconds:05.2f}"


def _format_timestamp(value: datetime) -> str:
    return value.strftime("%d.%m %H:%M")


class ProgressPresenter:
    """Render :class:`WeeklyProgressLike` payloads for chat delivery."""

    EMPTY_KEY = "presenter.progress.empty"
    HEADER_KEY = "presenter.progress.header"
    HIGHLIGHT_KEY = "presenter.progress.highlight"
    PR_BADGE_KEY = "presenter.progress.pr_badge"

    def __init__(
        self,
        *,
        translator: ProgressTranslator | None = None,
        seconds_formatter: Callable[[float], str] = _format_seconds,
        timestamp_formatter: Callable[[datetime], str] = _format_timestamp,
    ) -> None:
        self._t = translator or self._fallback_translator
        self._format_seconds = seconds_formatter
        self._format_timestamp = timestamp_formatter

    def render(self, view: WeeklyProgressLike, *, lang: str | None = None) -> str:
        if getattr(view, "attempts", 0) == 0:
            return self._t(self.EMPTY_KEY, lang=lang)

        header = self._t(
            self.HEADER_KEY,
            lang=lang,
            attempts=view.attempts,
            pr_count=getattr(view, "pr_count", 0),
        )
        lines = [header]
        for highlight in getattr(view, "highlights", ()) or ():
            lines.append(self._render_highlight(highlight, lang=lang))
        return "\n".join(lines)

    def _render_highlight(
        self, highlight: HighlightLike, *, lang: str | None
    ) -> str:
        badge = (
            self._t(self.PR_BADGE_KEY, lang=lang)
            if getattr(highlight, "is_pr", False)
            else ""
        )
        return self._t(
            self.HIGHLIGHT_KEY,
            lang=lang,
            stroke=highlight.stroke,
            distance=highlight.distance,
            time=self._format_seconds(highlight.total_seconds),
            timestamp=self._format_timestamp(highlight.timestamp),
            pr_badge=badge,
        )

    @staticmethod
    def _fallback_translator(
        key: str, /, *, lang: str | None = None, **params: object
    ) -> str:
        """English-only fallback used when no translator is wired in.

        Production code is expected to pass an i18n-backed translator;
        these strings exist purely to keep the presenter usable in
        scripts and tests without bootstrapping the i18n layer.
        """

        if key == ProgressPresenter.EMPTY_KEY:
            return "No attempts logged this week yet."
        if key == ProgressPresenter.HEADER_KEY:
            return (
                f"Week: {params.get('attempts', 0)} attempts, "
                f"{params.get('pr_count', 0)} PR"
            )
        if key == ProgressPresenter.HIGHLIGHT_KEY:
            badge = params.get("pr_badge") or ""
            distance_label = f"{params.get('distance')}m"
            return (
                f"- {params.get('stroke')} {distance_label} - "
                f"{params.get('time')} {badge} ({params.get('timestamp')})"
            ).strip()
        if key == ProgressPresenter.PR_BADGE_KEY:
            return "[PR]"
        return key


__all__ = [
    "HighlightLike",
    "ProgressPresenter",
    "ProgressTranslator",
    "WeeklyProgressLike",
]
