"""Utilities for analysing sprint progress and personal records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class TotalPRResult:
    """Information about overall personal record status."""

    previous: float | None
    current: float
    is_new: bool
    delta: float


@dataclass(frozen=True)
class SobStats:
    """Describe Sum of Best calculations for a result."""

    previous: float | None
    current: float
    delta: float


def calc_total_pr(previous_best: float | None, current_total: float) -> TotalPRResult:
    """Return total PR status comparing new total with the previous best."""

    is_new = previous_best is None or current_total < previous_best
    if is_new and previous_best is not None:
        delta = previous_best - current_total
    else:
        delta = 0.0
    return TotalPRResult(
        previous=previous_best,
        current=current_total,
        is_new=is_new,
        delta=delta,
    )


def calc_segment_prs(
    previous_bests: Sequence[float | None],
    new_segments: Sequence[float],
) -> list[bool]:
    """Return list of flags showing which segments improved."""

    results: list[bool] = []
    for idx, segment in enumerate(new_segments):
        prev = previous_bests[idx] if idx < len(previous_bests) else None
        results.append(prev is None or segment < prev)
    return results


def calc_sob(
    previous_bests: Sequence[float | None],
    new_segments: Sequence[float],
) -> SobStats:
    """Calculate Sum of Best metrics for provided segment times."""

    prev_values = [value for value in previous_bests if value is not None]
    previous = sum(prev_values) if prev_values else None
    max_len = max(len(previous_bests), len(new_segments))
    current_total = 0.0
    for idx in range(max_len):
        prev = previous_bests[idx] if idx < len(previous_bests) else None
        new = new_segments[idx] if idx < len(new_segments) else None
        if prev is None and new is None:
            continue
        if prev is None:
            best = new if new is not None else 0.0
        elif new is None:
            best = prev
        else:
            best = min(prev, new)
        current_total += best
    if previous is None:
        delta = 0.0
    else:
        delta = max(previous - current_total, 0.0)
    return SobStats(previous=previous, current=current_total, delta=delta)
