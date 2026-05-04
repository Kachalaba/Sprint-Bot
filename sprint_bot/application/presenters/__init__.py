"""Presenters render application use case output as user-facing text.

A presenter takes a typed view (``WeeklyProgressView``, ``ComparisonView`` …)
and produces an i18n-aware human-readable string. Keeping this layer free of
aiogram primitives means handlers can stay thin: they call a use case, hand
the resulting view to a presenter, then send the rendered text.
"""

from .progress import (
    HighlightLike,
    ProgressPresenter,
    ProgressTranslator,
    WeeklyProgressLike,
)

__all__ = [
    "HighlightLike",
    "ProgressPresenter",
    "ProgressTranslator",
    "WeeklyProgressLike",
]
