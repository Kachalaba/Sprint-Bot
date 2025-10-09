"""Image-based sprint report generator."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Sequence

import matplotlib

matplotlib.use("Agg")  # noqa: E402
from matplotlib import pyplot as plt  # noqa: E402

from i18n import t  # noqa: E402
from utils import fmt_time, speed  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SegmentReportRow:
    """Single table row describing segment performance."""

    time: float
    distance: float
    best: float | None = None

    @property
    def velocity(self) -> float:
        """Return segment speed in metres per second."""

        return speed(self.distance, self.time)

    @property
    def percent_to_best(self) -> float | None:
        """Return percentage difference to the best split (positive is slower)."""

        if self.best is None or self.best <= 0:
            return None
        return (self.time / self.best - 1) * 100

    @property
    def pace(self) -> float:
        """Return pace in seconds per 100 metres."""

        if not self.distance:
            return 0.0
        return self.time / self.distance * 100


@dataclass(frozen=True)
class AttemptReport:
    """Metadata required to render the sprint image report."""

    athlete_name: str
    stroke: str
    distance: int
    timestamp: str
    total_time: float
    segments: Sequence[SegmentReportRow]
    total_is_pr: bool = False
    sob_improved: bool = False

    def pace_values(self) -> list[float]:
        """Return pace values for plotting."""

        return [segment.pace for segment in self.segments]


_TITLE_COLOR = "#1f2937"
_TABLE_HEADER_COLOR = "#e5e7eb"
_TABLE_CELL_COLOR = "#f9fafb"
_CHART_COLOR = "#2563eb"
_GRID_COLOR = "#d1d5db"
_FOOTER_COLOR = "#4b5563"
_BACKGROUND_COLOR = "#ffffff"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 0:
        return f"+{value:.1f}%"
    return f"{value:.1f}%"


def _build_table(ax: plt.Axes, segments: Sequence[SegmentReportRow]) -> None:
    ax.axis("off")
    headers = [
        t("report.col.segment"),
        t("report.col.time"),
        t("report.col.ms"),
        t("report.col.percent_best"),
    ]
    cell_data: list[list[str]] = []
    for idx, segment in enumerate(segments, start=1):
        cell_data.append(
            [
                str(idx),
                fmt_time(segment.time),
                f"{segment.velocity:.2f}",
                _format_percent(segment.percent_to_best),
            ]
        )
    table = ax.table(
        cellText=cell_data,
        colLabels=headers,
        cellLoc="center",
        loc="upper left",
        colColours=[_TABLE_HEADER_COLOR] * len(headers),
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.6)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("white")
        if row == 0:
            cell.set_text_props(weight="bold", color=_TITLE_COLOR)
        else:
            cell.set_facecolor(_TABLE_CELL_COLOR)


def _build_chart(ax: plt.Axes, segments: Sequence[SegmentReportRow]) -> None:
    x_values = list(range(1, len(segments) + 1))
    y_values = [segment.pace for segment in segments]
    ax.plot(
        x_values,
        y_values,
        color=_CHART_COLOR,
        marker="o",
        linewidth=2,
    )
    ax.set_xlabel(t("report.col.segment"))
    ax.set_ylabel(t("report.chart.pace"))
    ax.grid(True, color=_GRID_COLOR, linewidth=0.8, linestyle="--", alpha=0.6)
    ax.set_xlim(0.8, len(segments) + 0.2)


def _build_footer(ax: plt.Axes, payload: AttemptReport) -> None:
    ax.axis("off")
    footer_lines = [
        f"{payload.timestamp} — {payload.athlete_name}",
        f"{payload.stroke}, {payload.distance} м",
        "{total}: {time} | {pr}: {pr_status} | {sob}: {sob_status}".format(
            total=t("report.footer.total"),
            time=fmt_time(payload.total_time),
            pr=t("report.footer.pr"),
            pr_status=(
                t("report.status.yes") if payload.total_is_pr else t("report.status.no")
            ),
            sob=t("report.footer.sob"),
            sob_status=(
                t("report.status.yes")
                if payload.sob_improved
                else t("report.status.no")
            ),
        ),
    ]
    ax.text(
        0.0,
        0.7,
        "\n".join(footer_lines),
        fontsize=11,
        color=_FOOTER_COLOR,
        va="top",
    )


def generate_image_report(payload: AttemptReport) -> bytes:
    """Render sprint report as PNG bytes."""

    if not payload.segments:
        raise ValueError("At least one segment is required to build the report")

    fig = plt.figure(figsize=(8, 6), dpi=100, facecolor=_BACKGROUND_COLOR)
    grid = fig.add_gridspec(3, 1, height_ratios=[1.4, 1.4, 0.6])

    table_ax = fig.add_subplot(grid[0])
    chart_ax = fig.add_subplot(grid[1])
    footer_ax = fig.add_subplot(grid[2])

    fig.suptitle(
        t("report.title", stroke=payload.stroke, distance=payload.distance),
        fontsize=16,
        color=_TITLE_COLOR,
        fontweight="bold",
        x=0.02,
        ha="left",
    )

    _build_table(table_ax, payload.segments)
    _build_chart(chart_ax, payload.segments)
    _build_footer(footer_ax, payload)

    fig.tight_layout(rect=(0, 0, 1, 0.94))

    buffer = io.BytesIO()
    try:
        fig.savefig(
            buffer,
            format="png",
            dpi=100,
            bbox_inches="tight",
            facecolor=_BACKGROUND_COLOR,
        )
    except Exception as exc:  # pragma: no cover - matplotlib backend issues
        logger.exception("Failed to render sprint image report: %s", exc)
        raise RuntimeError("Failed to render sprint image report") from exc
    finally:
        plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()
