"""Report generation utilities."""

from .image_report import AttemptReport, SegmentReportRow, generate_image_report

__all__ = [
    "AttemptReport",
    "SegmentReportRow",
    "generate_image_report",
]
