import math

import pytest

from utils.parse_time import parse_splits, parse_total, validate_splits


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("58.5", 58.5),
        ("0:58.50", 58.5),
        ("1:05", 65.0),
        ("1:05.3", 65.3),
        ("01:05.30", 65.3),
        (" 1:05.30 ", 65.3),
        ("58", 58.0),
    ],
)
def test_parse_total_valid_formats(raw: str, expected: float) -> None:
    assert math.isclose(parse_total(raw), expected, rel_tol=0, abs_tol=1e-9)


@pytest.mark.parametrize(
    "raw",
    ["", "abc", "1:65", "-1:00", "1:05:30"],
)
def test_parse_total_invalid_formats(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_total(raw)


def test_parse_splits_mixed_formats() -> None:
    values = parse_splits(["0:30.00", 32.5, "32.50", 30])
    assert values == [30.0, 32.5, 32.5, 30.0]


@pytest.mark.parametrize(
    "items",
    [
        [""],
        ["not-a-time"],
        [-1.0],
        ["0:30.00", -0.1],
    ],
)
def test_parse_splits_invalid(items: list[object]) -> None:
    with pytest.raises(ValueError):
        parse_splits(items)  # type: ignore[arg-type]


def test_validate_splits_within_tolerance() -> None:
    validate_splits(58.6, [30.0, 28.7])


@pytest.mark.parametrize(
    "total,splits",
    [
        (58.0, [30.0, 27.3]),
        (60.0, [30.5, 29.1]),
    ],
)
def test_validate_splits_mismatch(total: float, splits: list[float]) -> None:
    with pytest.raises(ValueError):
        validate_splits(total, splits, tol=0.20)


@pytest.mark.parametrize(
    "total,splits",
    [(-1.0, [30.0]), (60.0, [30.0, -1.0])],
)
def test_validate_splits_negative_values(total: float, splits: list[float]) -> None:
    with pytest.raises(ValueError):
        validate_splits(total, splits)
