"""Snapshot tests for sprint image report generation."""

from __future__ import annotations

import hashlib

from reports import AttemptReport, SegmentReportRow, generate_image_report


def test_generate_image_report_snapshot() -> None:
    """Generated image should remain stable across runs."""

    segments = [
        SegmentReportRow(time=12.45, distance=25.0, best=12.3),
        SegmentReportRow(time=12.80, distance=25.0, best=12.5),
        SegmentReportRow(time=13.10, distance=25.0, best=12.9),
        SegmentReportRow(time=13.50, distance=25.0, best=13.2),
    ]
    attempt = AttemptReport(
        athlete_name="Test Athlete",
        stroke="freestyle",
        distance=100,
        timestamp="2024-04-05 10:00:00",
        total_time=sum(segment.time for segment in segments),
        segments=segments,
        total_is_pr=True,
        sob_improved=True,
    )

    image_bytes = generate_image_report(attempt)

    assert len(image_bytes) < 150_000

    digest = hashlib.sha256(image_bytes).hexdigest()
    assert digest == "3924eb08b4a343051deba5e18c842ca9984ffbbdf6fcd78443db93505ca5d677"
