"""Swimming analytics helpers for Sprint-Bot.

The module defines canonical formulas for calculating speed-based metrics and
personal-record analytics. All public functions operate on sequences of split
values measured in seconds. Inputs may be provided as floats, integers,
``datetime.timedelta`` objects or strings in ``MM:SS.ss`` format. Distances are
expressed in metres.

Functions exported here are covered by doctests and pytest unit tests to ensure
numerical stability. They are also used by higher layers (services, handlers)
so keeping them pure and dependency-free is critical.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from utils.parse_time import parse_total

TimeInput = float | int | str | timedelta


def _to_seconds(value: TimeInput) -> float:
    """Convert supported time representation to seconds.

    Args:
        value: Float seconds, integer seconds, ``timedelta`` or ``MM:SS`` string.

    Returns:
        Normalised duration in seconds as a float.

    Raises:
        ValueError: If the value is negative or cannot be parsed.

    >>> _to_seconds(31.2)
    31.2
    >>> _to_seconds("0:28.50")
    28.5
    >>> _to_seconds(timedelta(seconds=17))
    17.0
    """

    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, timedelta):
        seconds = float(value.total_seconds())
    elif isinstance(value, str):
        seconds = float(parse_total(value))
    else:  # pragma: no cover - typing guard
        raise TypeError(f"unsupported time value: {type(value)!r}")

    if seconds < 0:
        raise ValueError("split times must be non-negative")
    return seconds


def _normalise_splits(values: Sequence[TimeInput]) -> tuple[float, ...]:
    """Return tuple of split values converted to seconds."""

    return tuple(_to_seconds(item) for item in values)


def _normalise_optional(
    values: Sequence[float | TimeInput | None],
) -> tuple[float | None, ...]:
    """Return tuple of optional split values converted to seconds."""

    result: list[float | None] = []
    for item in values:
        if item is None:
            result.append(None)
            continue
        result.append(_to_seconds(item))
    return tuple(result)


def _normalise_lengths(
    segment_length: float | Sequence[float], count: int
) -> tuple[float, ...]:
    """Normalise segment length input into a tuple of floats."""

    if isinstance(segment_length, Sequence) and not isinstance(
        segment_length, (str, bytes)
    ):
        lengths = tuple(float(length) for length in segment_length)
        if len(lengths) != count:
            raise ValueError("segment length sequence must match splits length")
    else:
        value = float(segment_length)
        if value <= 0:
            raise ValueError("segment_length must be positive")
        lengths = tuple(value for _ in range(count))

    if any(length <= 0 for length in lengths):
        raise ValueError("segment lengths must be positive")
    return lengths


@dataclass(slots=True, frozen=True)
class TotalPRResult:
    """Summary of total personal-record comparison."""

    previous: float | None
    current: float
    is_new: bool
    delta: float


@dataclass(slots=True, frozen=True)
class SobStats:
    """Describe Sum-of-Bests aggregation."""

    previous: float | None
    current: float
    delta: float


def segment_speeds(
    splits: Sequence[TimeInput],
    segment_length: float | Sequence[float],
) -> tuple[float, ...]:
    """Return instantaneous speeds for each split.

    Args:
        splits: Sequence of segment times in seconds.
        segment_length: Length of a single analysed segment in metres or a
            sequence of lengths matching ``splits``.

    Returns:
        Tuple with segment speeds in metres per second. Zero time results in
        zero speed.

    Raises:
        ValueError: If ``segment_length`` is not positive or splits are negative.

    >>> segment_speeds([31.0, 32.5], 25.0)
    (0.8064516129032258, 0.7692307692307693)
    >>> segment_speeds(["0:15.50", "0:16.00"], 12.5)
    (0.8064516129032258, 0.78125)
    >>> segment_speeds([14.0, 15.0], [25.0, 26.0])
    (1.7857142857142858, 1.7333333333333334)
    """

    splits_sec = _normalise_splits(splits)
    lengths = _normalise_lengths(segment_length, len(splits_sec))
    speeds: list[float] = []
    for seg_len, value in zip(lengths, splits_sec):
        speeds.append(0.0 if value == 0 else seg_len / value)
    return tuple(speeds)


def avg_speed(splits: Sequence[TimeInput], distance: float) -> float:
    """Return average speed for the full attempt.

    Args:
        splits: Sequence of split times in seconds.
        distance: Total race distance in metres.

    Returns:
        Average speed in metres per second (0.0 if total time is zero).

    Raises:
        ValueError: If ``distance`` is not positive or a split is negative.

    >>> avg_speed([30.5, 31.1], 100)
    1.6233766233766234
    >>> avg_speed(["0:27.50", "0:28.00"], 100)
    1.8018018018018018
    """

    if distance <= 0:
        raise ValueError("distance must be positive")
    splits_sec = _normalise_splits(splits)
    total = sum(splits_sec)
    return 0.0 if total == 0 else distance / total


def pace_per_100(
    splits: Sequence[TimeInput],
    segment_length: float | Sequence[float],
) -> tuple[float, ...]:
    """Return pace (seconds per 100 metres) for each segment.

    Args:
        splits: Sequence of split times.
        segment_length: Length of segment in metres or a sequence matching
            ``splits``.

    Returns:
        Tuple with pace values (``split_time / segment_length * 100``).

    Raises:
        ValueError: If ``segment_length`` is not positive or a split is negative.

    >>> pace_per_100([15.5, 16.0], 25.0)
    (62.0, 64.0)
    >>> pace_per_100(["0:17.80"], 25.0)
    (71.2,)
    >>> pace_per_100([30.0, 31.0], [50.0, 48.0])
    (60.0, 64.58333333333334)
    """

    splits_sec = _normalise_splits(splits)
    lengths = _normalise_lengths(segment_length, len(splits_sec))
    paces: list[float] = []
    for seg_len, value in zip(lengths, splits_sec):
        paces.append(value / seg_len * 100.0)
    return tuple(paces)


def degradation_percent(
    splits: Sequence[TimeInput],
    segment_length: float | Sequence[float],
) -> float:
    """Return speed degradation percentage between first and last segments.

    The value is computed as ``(v0 - vn) / v0 * 100`` where ``v0`` is the speed
    on the first segment and ``vn`` is the speed on the last segment. If fewer
    than two splits are provided or the first speed is zero the degradation is
    reported as ``0.0``.

    >>> round(degradation_percent([30.0, 32.0], 25.0), 2)
    6.25
    >>> degradation_percent([30.0], 25.0)
    0.0
    """

    speeds = segment_speeds(splits, segment_length)
    if len(speeds) < 2:
        return 0.0
    first = speeds[0]
    last = speeds[-1]
    if first == 0:
        return 0.0
    return max((first - last) / first * 100.0, 0.0)


def detect_total_pr(
    previous_best: TimeInput | None, current_total: TimeInput
) -> TotalPRResult:
    """Compare totals and determine whether a new personal record was set.

    >>> detect_total_pr(65.3, 64.9)
    TotalPRResult(previous=65.3, current=64.9, is_new=True, delta=0.3999999999999915)
    >>> detect_total_pr(None, 70.0).is_new
    True
    >>> detect_total_pr(70.0, 70.5).delta
    0.0
    """

    current = _to_seconds(current_total)
    previous = None if previous_best is None else _to_seconds(previous_best)
    is_new = previous is None or current < previous
    delta = previous - current if is_new and previous is not None else 0.0
    return TotalPRResult(previous=previous, current=current, is_new=is_new, delta=delta)


def detect_segment_prs(
    previous_bests: Sequence[TimeInput | None],
    new_segments: Sequence[TimeInput],
) -> tuple[bool, ...]:
    """Return flags indicating which segments improved.

    The result length matches ``new_segments`` length. Missing previous bests
    are treated as infinite (so the segment counts as an improvement).

    >>> detect_segment_prs([30.0, None], [29.5, 30.2])
    (True, True)
    >>> detect_segment_prs([28.0, 31.0, 32.0], [28.2, 30.5])
    (False, True)
    """

    previous = _normalise_optional(previous_bests)
    current = _normalise_splits(new_segments)
    result: list[bool] = []
    for idx, split in enumerate(current):
        prev = previous[idx] if idx < len(previous) else None
        result.append(prev is None or split < prev)
    return tuple(result)


def calc_sob(
    previous_bests: Sequence[TimeInput | None],
    new_segments: Sequence[TimeInput],
) -> SobStats:
    """Calculate Sum-of-Bests metric for provided splits.

    The Sum-of-Bests is the sum of the best time observed for each segment.
    When a previous best is missing the new split is used. Extra previous
    segments without a corresponding new split retain their previous value.

    >>> sob = calc_sob([30.0, 31.0, None], [29.8, 31.5])
    >>> round(sob.current, 2)
    60.8
    >>> sob.delta
    0.20000000000000284
    >>> calc_sob([], [30.0]).previous is None
    True
    """

    previous = _normalise_optional(previous_bests)
    current = _normalise_splits(new_segments)

    previous_sum: float | None
    prev_values = [value for value in previous if value is not None]
    previous_sum = sum(prev_values) if prev_values else None

    max_len = max(len(previous), len(current)) if previous or current else 0
    total = 0.0
    for idx in range(max_len):
        prev = previous[idx] if idx < len(previous) else None
        new = current[idx] if idx < len(current) else None
        if prev is None and new is None:
            continue
        if prev is None:
            best = new if new is not None else 0.0
        elif new is None:
            best = prev
        else:
            best = min(prev, new)
        total += best

    delta = 0.0 if previous_sum is None else max(previous_sum - total, 0.0)
    return SobStats(previous=previous_sum, current=total, delta=delta)


__all__ = [
    "TimeInput",
    "TotalPRResult",
    "SobStats",
    "segment_speeds",
    "avg_speed",
    "pace_per_100",
    "degradation_percent",
    "detect_total_pr",
    "detect_segment_prs",
    "calc_sob",
]
