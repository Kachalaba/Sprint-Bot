"""Turn analytics utilities for swim workouts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable

__all__ = ["TurnMetrics", "TurnService"]


from utils.logger import get_logger

_LOGGER = get_logger(__name__)


@dataclass
class TurnMetrics:
    """Time breakdown for a single turn."""

    approach_time: float
    wall_contact_time: float
    push_off_time: float
    underwater_time: float
    efficiency_score: float


class TurnService:
    """Analyse turns, calculate efficiency and produce recommendations."""

    _TURN_TIME_NORMS: dict[str, dict[str, float]] = {
        "freestyle": {
            "approach": 3.4,
            "contact": 0.55,
            "push_off": 0.75,
            "underwater": 3.6,
        },
        "backstroke": {
            "approach": 3.7,
            "contact": 0.6,
            "push_off": 0.8,
            "underwater": 3.8,
        },
        "breaststroke": {
            "approach": 3.9,
            "contact": 0.75,
            "push_off": 0.95,
            "underwater": 3.0,
        },
        "butterfly": {
            "approach": 3.6,
            "contact": 0.65,
            "push_off": 0.85,
            "underwater": 4.1,
        },
    }

    _STROKE_ALIASES: dict[str, str] = {
        "free": "freestyle",
        "crawl": "freestyle",
        "front crawl": "freestyle",
        "back": "backstroke",
        "backstroke": "backstroke",
        "breaststroke": "breaststroke",
        "breast": "breaststroke",
        "butterfly": "butterfly",
        "fly": "butterfly",
    }

    def __init__(self) -> None:
        self._metric_strokes: dict[int, str] = {}
        self._lock = asyncio.Lock()

    async def analyze_turn(
        self, stroke: str, segment_times: Iterable[float]
    ) -> TurnMetrics:
        """Calculate detailed metrics for the given stroke turn."""

        stroke_key = self._normalize_stroke(stroke)
        segments = list(segment_times)
        if len(segments) < 4:
            raise ValueError("segment_times must contain at least 4 values")

        metrics = TurnMetrics(
            approach_time=float(segments[0]),
            wall_contact_time=float(segments[1]),
            push_off_time=float(segments[2]),
            underwater_time=float(segments[3]),
            efficiency_score=0.0,
        )
        setattr(metrics, "_stroke_key", stroke_key)

        async with self._lock:
            self._metric_strokes[id(metrics)] = stroke_key

        efficiency = await self.calculate_turn_efficiency(metrics)
        metrics.efficiency_score = efficiency

        _LOGGER.info(
            "Turn analysed",
            extra={
                "stroke": stroke_key,
                "approach": metrics.approach_time,
                "contact": metrics.wall_contact_time,
                "push_off": metrics.push_off_time,
                "underwater": metrics.underwater_time,
                "efficiency": efficiency,
            },
        )

        return metrics

    async def calculate_turn_efficiency(self, turn_metrics: TurnMetrics) -> float:
        """Return efficiency score based on reference segment norms."""

        stroke_key = getattr(turn_metrics, "_stroke_key", None)
        if stroke_key is None:
            async with self._lock:
                stroke_key = self._metric_strokes.get(id(turn_metrics))
        if stroke_key is None:
            raise ValueError("TurnMetrics must be associated with a stroke")

        norms = self._TURN_TIME_NORMS.get(stroke_key)
        if norms is None:
            raise ValueError(f"No norms configured for stroke '{stroke_key}'")

        scores = []
        for actual, key in (
            (turn_metrics.approach_time, "approach"),
            (turn_metrics.wall_contact_time, "contact"),
            (turn_metrics.push_off_time, "push_off"),
            (turn_metrics.underwater_time, "underwater"),
        ):
            norm = norms[key]
            if actual <= 0:
                segment_score = 0.0
            else:
                ratio = norm / actual
                segment_score = max(0.0, min(ratio, 1.0))
            scores.append(segment_score)

        base_score = sum(scores) / len(scores) * 100

        if stroke_key == "breaststroke":
            base_score -= self._breaststroke_penalty(turn_metrics)
        elif stroke_key == "butterfly":
            base_score -= self._butterfly_penalty(turn_metrics)

        return round(max(0.0, min(base_score, 100.0)), 2)

    async def get_turn_recommendations(self, stroke: str, metrics: TurnMetrics) -> str:
        """Generate coaching tips based on metrics and stroke specifics."""

        stroke_key = self._normalize_stroke(stroke)
        norms = self._TURN_TIME_NORMS[stroke_key]
        recommendations: list[str] = []

        if metrics.approach_time > norms["approach"] * 1.1:
            recommendations.append(
                "Hold speed into the wall by tightening the final approach."
            )
        if metrics.wall_contact_time > norms["contact"] * 1.2:
            recommendations.append(
                "Reduce wall contact time by preparing the body position earlier."
            )
        if metrics.push_off_time > norms["push_off"] * 1.15:
            recommendations.append(
                "Focus on a stronger push-off to start the breakout with momentum."
            )
        if metrics.underwater_time < norms["underwater"] * 0.8:
            recommendations.append(
                "Extend the underwater phase with deeper glide and control."
            )

        if stroke_key == "breaststroke":
            if metrics.wall_contact_time < 0.6:
                recommendations.append(
                    "Ensure a clear two-hand touch before initiating the breaststroke turn."
                )
            if not 2.2 <= metrics.underwater_time <= 3.6:
                recommendations.append(
                    "Use one powerful breaststroke kick followed by streamlined glide underwater."
                )
        elif stroke_key == "butterfly":
            if metrics.wall_contact_time < 0.5:
                recommendations.append(
                    "Maintain the required two-hand touch before the butterfly turn."
                )
            if metrics.underwater_time < 3.2:
                recommendations.append(
                    "Add a couple of decisive dolphin kicks before surfacing."
                )

        if not recommendations:
            return "Turn executed efficiently, keep up the consistency."
        return "\n".join(recommendations)

    def _normalize_stroke(self, stroke: str) -> str:
        key = stroke.strip().lower()
        if key in self._TURN_TIME_NORMS:
            return key
        try:
            return self._STROKE_ALIASES[key]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise ValueError(f"Unsupported stroke '{stroke}'") from exc

    @staticmethod
    def _breaststroke_penalty(metrics: TurnMetrics) -> float:
        penalty = 0.0
        if metrics.wall_contact_time < 0.55:
            penalty += 8.0
        elif metrics.wall_contact_time > 0.9:
            penalty += 5.0
        if metrics.underwater_time < 2.0 or metrics.underwater_time > 3.8:
            penalty += 7.0
        return penalty

    @staticmethod
    def _butterfly_penalty(metrics: TurnMetrics) -> float:
        penalty = 0.0
        if metrics.wall_contact_time < 0.45:
            penalty += 6.0
        if metrics.underwater_time < 3.0:
            penalty += 6.0
        elif metrics.underwater_time > 4.6:
            penalty += 4.0
        return penalty
