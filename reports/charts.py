"""Chart builders for export commands."""

from __future__ import annotations

import io
import statistics
from collections import defaultdict
from typing import Sequence

import matplotlib  # noqa: E402

matplotlib.use("Agg")  # noqa: E402
from matplotlib import pyplot as plt  # noqa: E402

from i18n import t  # noqa: E402

from .data_export import ResultRecord  # noqa: E402

__all__ = [
    "build_progress_chart",
    "build_segment_speed_chart",
]


def _resolve_segment_lengths(
    distance: int,
    segments_count: int,
) -> Sequence[float]:
    if segments_count <= 0:
        return ()
    if distance <= 0:
        return (0.0,) * segments_count
    average = distance / segments_count
    return (float(average),) * segments_count


def _ensure_records(records: Sequence[ResultRecord]) -> Sequence[ResultRecord]:
    if not records:
        raise ValueError("No results available for plotting")
    return records


def _render_figure(fig) -> bytes:
    buffer = io.BytesIO()
    try:
        fig.tight_layout()
        fig.savefig(buffer, format="png", dpi=150)
    finally:
        plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()


def build_segment_speed_chart(records: Sequence[ResultRecord]) -> bytes:
    """Return PNG graph with average speed per segment."""

    _ensure_records(records)
    segments: dict[int, list[float]] = defaultdict(list)
    for record in records:
        lengths = _resolve_segment_lengths(
            record.distance,
            len(record.segments),
        )
        pairs = zip(lengths, record.segments)
        for idx, (length, split) in enumerate(pairs, start=1):
            if split <= 0 or length <= 0:
                continue
            segments[idx].append(length / split)
    if not segments:
        raise ValueError("No segment splits recorded for selected filters")
    indices = sorted(segments)
    avg_speeds = [statistics.fmean(segments[idx]) for idx in indices]
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)
    ax.bar(indices, avg_speeds, color="#2563eb")
    ax.set_xlabel(t("report.col.segment"))
    ax.set_ylabel(t("report.chart.speed"))
    ax.set_title(t("report.export.speed_title"))
    ax.grid(axis="y", linestyle="--", linewidth=0.8, alpha=0.4)
    ax.set_ylim(bottom=0)
    return _render_figure(fig)


def build_progress_chart(records: Sequence[ResultRecord]) -> bytes:
    """Return PNG graph illustrating total time trend."""

    items = _ensure_records(records)
    sorted_items = sorted(items, key=lambda record: record.timestamp)
    timestamps = [record.timestamp for record in sorted_items]
    totals = [record.total_seconds for record in sorted_items]
    labels = [timestamp.strftime("%Y-%m-%d") for timestamp in timestamps]
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=120)
    ax.plot(labels, totals, color="#059669", marker="o", linewidth=2)
    ax.set_xlabel(t("report.export.date"))
    ax.set_ylabel(t("report.export.total"))
    ax.set_title(t("report.export.progress_title"))
    ax.grid(True, linestyle="--", linewidth=0.8, alpha=0.4)
    ax.set_ylim(bottom=min(totals) * 0.9 if totals else 0)
    ax.tick_params(axis="x", rotation=45)
    return _render_figure(fig)
