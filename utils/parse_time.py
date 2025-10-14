"""Helpers for parsing and validating swim times."""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterable, Mapping, Sequence

_TIME_RE = re.compile(
    r"""
    ^\s*
    (?:(?P<minutes>\d+):(?P<seconds>\d{1,2})(?:[.,](?P<fraction>\d{1,3}))?|
       (?P<plain>\d+(?:[.,]\d+)?)
    )
    \s*$
    """,
    re.VERBOSE,
)


class ParseTimeErrorCode(str, Enum):
    """Translation keys for time parsing errors."""

    INVALID_TIME = "error.invalid_time"
    INVALID_INPUT = "error.invalid_input"
    SPLITS_MISMATCH = "error.splits_mismatch"


class ParseTimeError(ValueError):
    """Exception that carries a translation key for parse-time failures."""

    def __init__(
        self,
        code: ParseTimeErrorCode,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.context: Mapping[str, object] = dict(context or {})
        super().__init__(code.value)


def parse_total(raw: str) -> float:
    """Parse total swim time from a string into seconds."""

    text = raw.strip()
    if not text:
        raise ParseTimeError(
            ParseTimeErrorCode.INVALID_TIME, context={"value": raw}
        )

    match = _TIME_RE.match(text)
    if not match:
        raise ParseTimeError(
            ParseTimeErrorCode.INVALID_TIME, context={"value": raw}
        )

    plain = match.group("plain")
    if plain is not None:
        plain = plain.replace(",", ".")
        value = float(plain)
    else:
        minutes = int(match.group("minutes"))
        seconds = int(match.group("seconds"))
        if seconds >= 60:
            raise ParseTimeError(
                ParseTimeErrorCode.INVALID_TIME, context={"value": raw}
            )
        fraction = match.group("fraction") or ""
        frac_value = int(fraction) / (10 ** len(fraction)) if fraction else 0.0
        value = minutes * 60 + seconds + frac_value

    if value < 0:
        raise ParseTimeError(
            ParseTimeErrorCode.INVALID_TIME, context={"value": raw}
        )

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
            raise ParseTimeError(
                ParseTimeErrorCode.INVALID_INPUT, context={"value": item}
            )

        if value < 0:
            raise ParseTimeError(
                ParseTimeErrorCode.INVALID_TIME, context={"value": item}
            )
        parsed.append(value)

    return parsed


def validate_splits(total: float, splits: Iterable[float], tol: float = 0.20) -> None:
    """Validate that the sum of splits matches the total within tolerance."""

    if tol < 0:
        raise ParseTimeError(ParseTimeErrorCode.INVALID_INPUT, context={"tol": tol})
    if total < 0:
        raise ParseTimeError(
            ParseTimeErrorCode.INVALID_TIME, context={"value": total}
        )

    splits_list = list(splits)
    if any(value < 0 for value in splits_list):
        raise ParseTimeError(
            ParseTimeErrorCode.INVALID_TIME,
            context={"value": next(value for value in splits_list if value < 0)},
        )

    diff = abs(sum(splits_list) - total)
    if diff > tol:
        raise ParseTimeError(
            ParseTimeErrorCode.SPLITS_MISMATCH,
            context={"diff": diff},
        )
