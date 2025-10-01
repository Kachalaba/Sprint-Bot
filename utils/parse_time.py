"""Helpers for parsing and validating swim times."""

from __future__ import annotations

import re
from typing import Iterable, Sequence

_TIME_RE = re.compile(
    r"""
    ^\s*
    (?:(?P<minutes>\d+):(?P<seconds>\d{1,2})(?:\.(?P<fraction>\d{1,3}))?|
       (?P<plain>\d+(?:\.\d+)?)
    )
    \s*$
    """,
    re.VERBOSE,
)


def parse_total(raw: str) -> float:
    """Parse total swim time from a string into seconds."""

    text = raw.strip()
    if not text:
        raise ValueError("time value is empty")

    match = _TIME_RE.match(text)
    if not match:
        raise ValueError(f"invalid time format: {raw!r}")

    plain = match.group("plain")
    if plain is not None:
        value = float(plain)
    else:
        minutes = int(match.group("minutes"))
        seconds = int(match.group("seconds"))
        if seconds >= 60:
            raise ValueError("seconds part must be less than 60")
        fraction = match.group("fraction") or ""
        frac_value = int(fraction) / (10 ** len(fraction)) if fraction else 0.0
        value = minutes * 60 + seconds + frac_value

    if value < 0:
        raise ValueError("time value must be non-negative")

    return value


def parse_splits(items: Sequence[str | float | int]) -> list[float]:
    """Parse collection of split values to floats."""

    parsed: list[float] = []
    for item in items:
        if isinstance(item, str):
            value = parse_total(item)
        elif isinstance(item, (int, float)):
            value = float(item)
        else:
            raise ValueError(f"unsupported split value: {item!r}")

        if value < 0:
            raise ValueError("split value must be non-negative")
        parsed.append(value)

    return parsed


def validate_splits(total: float, splits: Iterable[float], tol: float = 0.20) -> None:
    """Validate that the sum of splits matches the total within tolerance."""

    if tol < 0:
        raise ValueError("tolerance must be non-negative")
    if total < 0:
        raise ValueError("total time must be non-negative")

    splits_list = list(splits)
    if any(value < 0 for value in splits_list):
        raise ValueError("split values must be non-negative")

    diff = abs(sum(splits_list) - total)
    if diff > tol:
        raise ValueError("sum of splits does not match total within tolerance")
