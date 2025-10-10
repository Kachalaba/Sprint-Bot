"""Team analytics and comparison helpers."""

from __future__ import annotations

import asyncio
import io
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from services.pb_service import get_latest_attempt, get_sob
from utils import fmt_time, get_segments
from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_DB_PATH = Path("data/results.db")


@dataclass(frozen=True, slots=True)
class AthleteComparison:
    """Per-athlete comparison payload."""

    athlete_id: int
    athlete_name: str
    total_time: float
    segments: tuple[float, ...]
    pace: tuple[float, ...]
    sob_segments: tuple[float, ...]
    sob_total: float | None


@dataclass(frozen=True, slots=True)
class TeamComparison:
    """Result of comparing a group of athletes."""

    stroke: str
    distance: int
    athletes: tuple[AthleteComparison, ...]
    average_pace: tuple[float, ...]


class TeamAnalyticsService:
    """Build comparison summaries for a group of athletes."""

    def __init__(self, db_path: Path | str = _DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)

    async def compare_team(
        self,
        athlete_ids: Sequence[int],
        stroke: str,
        distance: int,
        *,
        profiles: Sequence[dict] | None = None,
        group: str | None = None,
        club: str | None = None,
    ) -> TeamComparison:
        """Compare latest attempts for athletes and return summary."""

        filtered_ids = self._filter_athletes(athlete_ids, profiles, group, club)
        if not filtered_ids:
            raise ValueError("No athletes available after applying filters")

        return await asyncio.to_thread(
            self._compare_sync, tuple(filtered_ids), stroke, distance
        )

    def _filter_athletes(
        self,
        athlete_ids: Sequence[int],
        profiles: Sequence[dict] | None,
        group: str | None,
        club: str | None,
    ) -> list[int]:
        if not profiles or (group is None and club is None):
            return [int(aid) for aid in athlete_ids]
        allowed: set[int] = set()
        for profile in profiles:
            try:
                aid = int(profile.get("athlete_id"))
            except (TypeError, ValueError):
                continue
            if aid not in athlete_ids:
                continue
            if group is not None and profile.get("group") != group:
                continue
            if club is not None and profile.get("club") != club:
                continue
            allowed.add(aid)
        return [aid for aid in athlete_ids if aid in allowed]

    def _compare_sync(
        self, athlete_ids: Sequence[int], stroke: str, distance: int
    ) -> TeamComparison:
        stroke_norm = stroke.strip().lower()
        athletes: list[AthleteComparison] = []
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            for athlete_id in athlete_ids:
                latest = get_latest_attempt(
                    athlete_id, stroke_norm, distance, db_path=self._path
                )
                if latest is None:
                    logger.info(
                        "Skipping athlete %s due to missing latest attempt", athlete_id
                    )
                    continue
                segment_lengths = _resolve_segment_lengths(
                    distance, len(latest.segments)
                )
                name_row = conn.execute(
                    """
                    SELECT athlete_name FROM results
                    WHERE athlete_id = ? AND stroke = ? AND distance = ?
                    ORDER BY timestamp DESC, id DESC LIMIT 1
                    """,
                    (athlete_id, stroke_norm, distance),
                ).fetchone()
                athlete_name = (
                    str(name_row["athlete_name"])
                    if name_row and name_row["athlete_name"]
                    else f"ID {athlete_id}"
                )
                sob = get_sob(athlete_id, stroke_norm, distance, db_path=self._path)
                pace = tuple(
                    _calculate_pace(segment_time, segment_lengths[idx])
                    for idx, segment_time in enumerate(latest.segments)
                )
                athletes.append(
                    AthleteComparison(
                        athlete_id=athlete_id,
                        athlete_name=athlete_name,
                        total_time=latest.total,
                        segments=latest.segments,
                        pace=pace,
                        sob_segments=sob.segments,
                        sob_total=sob.total,
                    )
                )

        if not athletes:
            raise ValueError("No attempts found for provided athletes")

        max_len = max(len(item.pace) for item in athletes)
        average: list[float] = []
        for idx in range(max_len):
            values = [item.pace[idx] for item in athletes if idx < len(item.pace)]
            average.append(fmean(values) if values else 0.0)
        return TeamComparison(
            stroke=stroke_norm,
            distance=distance,
            athletes=tuple(athletes),
            average_pace=tuple(average),
        )

    async def build_chart(
        self,
        comparison: TeamComparison,
    ) -> bytes:
        """Render team comparison chart as PNG bytes."""

        return await asyncio.to_thread(self._build_chart_sync, comparison)

    def _build_chart_sync(self, comparison: TeamComparison) -> bytes:
        fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
        for athlete in comparison.athletes:
            xs = list(range(1, len(athlete.pace) + 1))
            ax.plot(
                xs, athlete.pace, marker="o", linewidth=1.8, label=athlete.athlete_name
            )
        if comparison.average_pace:
            ax.plot(
                list(range(1, len(comparison.average_pace) + 1)),
                comparison.average_pace,
                linestyle="--",
                linewidth=2.5,
                color="#111827",
                label="Team avg",
            )
        ax.set_title(
            f"Team pace - {comparison.distance} m {comparison.stroke}", fontsize=14
        )
        ax.set_xlabel("Segment")
        ax.set_ylabel("Pace (s/100m)")
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend()

        buffer = io.BytesIO()
        try:
            fig.tight_layout()
            fig.savefig(buffer, format="png", dpi=150)
        except Exception as exc:  # pragma: no cover - matplotlib backend issues
            logger.exception("Failed to render team chart: %s", exc)
            raise RuntimeError("Failed to render team chart") from exc
        finally:
            plt.close(fig)
        buffer.seek(0)
        return buffer.getvalue()

    def build_summary(self, comparison: TeamComparison) -> str:
        """Compose textual summary for comparison."""

        lines = [
            "Team comparison:",
            f"Stroke: {comparison.stroke}, distance: {comparison.distance} m",
        ]
        for athlete in comparison.athletes:
            sob_line = (
                fmt_time(athlete.sob_total) if athlete.sob_total is not None else "—"
            )
            lines.append(
                "{name}: {total} • SoB {sob}".format(
                    name=athlete.athlete_name,
                    total=fmt_time(athlete.total_time),
                    sob=sob_line,
                )
            )
        return "\n".join(lines)


def _resolve_segment_lengths(distance: int, count: int) -> tuple[float, ...]:
    defaults = [float(value) for value in get_segments(distance)]
    if count <= 0:
        return tuple()
    if len(defaults) == count:
        return tuple(defaults)
    if not defaults:
        average = distance / count if distance else 0.0
        return tuple(average for _ in range(count))
    if len(defaults) > count:
        return tuple(defaults[:count])
    average = distance / count if count else 0.0
    return tuple(defaults + [average] * (count - len(defaults)))


def _calculate_pace(time_value: float, distance: float) -> float:
    if distance <= 0:
        return 0.0
    return time_value / distance * 100


__all__ = [
    "AthleteComparison",
    "TeamAnalyticsService",
    "TeamComparison",
]
