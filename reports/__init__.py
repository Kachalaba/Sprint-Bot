"""Report generation utilities."""

from .cache import CacheSettings, ReportCache
from .charts import build_progress_chart, build_segment_speed_chart
from .data_export import (
    ExportFilters,
    ResultRecord,
    build_cache_key,
    export_results,
    load_results,
)
from .image_report import AttemptReport, SegmentReportRow, generate_image_report

__all__ = [
    "AttemptReport",
    "CacheSettings",
    "ExportFilters",
    "ReportCache",
    "ResultRecord",
    "SegmentReportRow",
    "build_cache_key",
    "build_progress_chart",
    "build_segment_speed_chart",
    "export_results",
    "generate_image_report",
    "load_results",
]
