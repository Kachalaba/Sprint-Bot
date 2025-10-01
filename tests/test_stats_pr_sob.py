"""Unit tests for statistics helper functions."""

from __future__ import annotations

import pytest

from services.stats_service import calc_segment_prs, calc_sob, calc_total_pr


def test_calc_total_pr_detects_improvement() -> None:
    result = calc_total_pr(60.0, 59.3)
    assert result.is_new
    assert result.previous == pytest.approx(60.0)
    assert result.current == pytest.approx(59.3)
    assert result.delta == pytest.approx(0.7)


def test_calc_total_pr_without_previous() -> None:
    result = calc_total_pr(None, 62.0)
    assert result.is_new
    assert result.previous is None
    assert result.delta == pytest.approx(0.0)


def test_calc_total_pr_no_improvement() -> None:
    result = calc_total_pr(58.0, 58.0)
    assert not result.is_new
    assert result.delta == pytest.approx(0.0)


def test_calc_segment_prs_flags() -> None:
    flags = calc_segment_prs([30.0, 31.2, None], [29.5, 31.5, 32.0])
    assert flags == [True, False, True]


def test_calc_sob_improvement() -> None:
    stats = calc_sob([30.0, 31.0, 32.5], [29.8, 30.5, 32.6])
    assert stats.previous == pytest.approx(93.5)
    assert stats.current == pytest.approx(92.8)
    assert stats.delta == pytest.approx(0.7)


def test_calc_sob_handles_missing_previous() -> None:
    stats = calc_sob([], [30.0, 31.0])
    assert stats.previous is None
    assert stats.current == pytest.approx(61.0)
    assert stats.delta == pytest.approx(0.0)


def test_calc_sob_with_shorter_new_result() -> None:
    stats = calc_sob([28.0, 29.0, 30.0], [27.5, 30.0])
    assert stats.previous == pytest.approx(87.0)
    assert stats.current == pytest.approx(86.5)
    assert stats.delta == pytest.approx(0.5)
