"""Unit tests for :mod:`sprint_bot.domain.analytics`."""

from __future__ import annotations

import doctest
from datetime import timedelta

import pytest

from sprint_bot.domain import analytics


def test_doctests_pass() -> None:
    """Ensure doctests stay in sync with implementation."""

    results = doctest.testmod(analytics)
    assert results.failed == 0


def test_segment_speeds_constant_length() -> None:
    speeds = analytics.segment_speeds([30.0, 32.0], 25.0)
    assert speeds == pytest.approx((0.8333333333333334, 0.78125))


def test_segment_speeds_variable_length_and_errors() -> None:
    speeds = analytics.segment_speeds([30.0, "0:31.0"], (25.0, 26.0))
    assert speeds == pytest.approx((0.8333333333333334, 0.8387096774193549))

    with pytest.raises(ValueError):
        analytics.segment_speeds([30.0], (25.0, 26.0))


def test_avg_speed_and_invalid_distance() -> None:
    assert analytics.avg_speed([10.0, 10.0], 40.0) == pytest.approx(2.0)
    assert analytics.avg_speed([0.0, 0.0], 50.0) == 0.0
    with pytest.raises(ValueError):
        analytics.avg_speed([10.0], 0)


def test_pace_per_100_handles_lengths() -> None:
    assert analytics.pace_per_100([30.0], 50.0) == (60.0,)
    assert analytics.pace_per_100([30.0, 32.0], [50.0, 48.0]) == pytest.approx(
        (60.0, 66.66666666666666)
    )
    with pytest.raises(ValueError):
        analytics.pace_per_100([30.0], [-50.0])


def test_degradation_percent_cases() -> None:
    assert analytics.degradation_percent([30.0, 32.0], 25.0) == pytest.approx(6.25)
    assert analytics.degradation_percent([30.0], 25.0) == 0.0
    assert analytics.degradation_percent([0.0, 30.0], 25.0) == 0.0
    assert analytics.degradation_percent([30.0, 28.0], 25.0) == 0.0


def test_detect_total_pr_variations() -> None:
    result = analytics.detect_total_pr(65.0, 64.5)
    assert result.is_new and result.delta == pytest.approx(0.5)

    result = analytics.detect_total_pr(None, timedelta(seconds=70))
    assert result.is_new and result.previous is None

    result = analytics.detect_total_pr(64.0, "1:04.00")
    assert not result.is_new and result.delta == pytest.approx(0.0)


def test_detect_segment_prs_and_invalid_values() -> None:
    flags = analytics.detect_segment_prs([30.0, None, "0:32.1"], [29.5, 31.0, 32.0])
    assert flags == (True, True, True)

    with pytest.raises(ValueError):
        analytics.detect_segment_prs([30.0], [-1.0])


def test_calc_sob_edge_cases() -> None:
    stats = analytics.calc_sob([30.0, 31.0, 32.5], [29.5, 30.5, 32.0])
    assert stats.previous == pytest.approx(93.5)
    assert stats.current == pytest.approx(92.0)
    assert stats.delta == pytest.approx(1.5)

    stats = analytics.calc_sob([], [])
    assert stats.previous is None and stats.current == pytest.approx(0.0)

    stats = analytics.calc_sob([30.0, None, 32.0], [29.5, 31.5, 32.2])
    assert stats.previous == pytest.approx(62.0)
    assert stats.current == pytest.approx(93.0)
    assert stats.delta == pytest.approx(0.0)

    stats = analytics.calc_sob([None, 32.0], [30.0])
    assert stats.previous == pytest.approx(32.0)
    assert stats.current == pytest.approx(62.0)

    with pytest.raises(ValueError):
        analytics.calc_sob([30.0], [29.5, -1.0])
