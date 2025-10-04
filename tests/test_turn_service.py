from __future__ import annotations

import asyncio

import pytest

from services.turn_service import TurnMetrics, TurnService


def test_analyze_turn_metrics_and_efficiency() -> None:
    async def scenario() -> None:
        service = TurnService()
        metrics = await service.analyze_turn("Freestyle", [3.4, 0.55, 0.75, 3.6])

        assert metrics.approach_time == pytest.approx(3.4)
        assert metrics.wall_contact_time == pytest.approx(0.55)
        assert metrics.push_off_time == pytest.approx(0.75)
        assert metrics.underwater_time == pytest.approx(3.6)
        assert metrics.efficiency_score == pytest.approx(100.0)

    asyncio.run(scenario())


def test_turn_recommendations_for_strokes() -> None:
    async def scenario() -> None:
        service = TurnService()

        breast_metrics = TurnMetrics(
            approach_time=5.0,
            wall_contact_time=0.5,
            push_off_time=1.1,
            underwater_time=1.5,
            efficiency_score=0.0,
        )
        breast_recs = await service.get_turn_recommendations(
            "breaststroke", breast_metrics
        )

        assert "Hold speed into the wall" in breast_recs
        assert "two-hand touch" in breast_recs
        assert "Use one powerful breaststroke kick" in breast_recs

        fly_metrics = TurnMetrics(
            approach_time=4.5,
            wall_contact_time=0.4,
            push_off_time=1.1,
            underwater_time=2.5,
            efficiency_score=0.0,
        )
        fly_recs = await service.get_turn_recommendations("butterfly", fly_metrics)

        assert "two-hand touch" in fly_recs
        assert "dolphin kicks" in fly_recs

    asyncio.run(scenario())


def test_analyze_turn_requires_complete_segments() -> None:
    async def scenario() -> None:
        service = TurnService()
        with pytest.raises(ValueError):
            await service.analyze_turn("freestyle", [3.0, 0.5])

    asyncio.run(scenario())


def test_calculate_efficiency_without_stroke_association() -> None:
    async def scenario() -> None:
        service = TurnService()
        metrics = TurnMetrics(
            approach_time=3.0,
            wall_contact_time=0.5,
            push_off_time=0.7,
            underwater_time=3.0,
            efficiency_score=0.0,
        )
        with pytest.raises(ValueError):
            await service.calculate_turn_efficiency(metrics)

    asyncio.run(scenario())


def test_unknown_stroke_rejected() -> None:
    async def scenario() -> None:
        service = TurnService()
        metrics = TurnMetrics(
            approach_time=3.5,
            wall_contact_time=0.6,
            push_off_time=0.8,
            underwater_time=3.5,
            efficiency_score=0.0,
        )
        with pytest.raises(ValueError):
            await service.get_turn_recommendations("sidestroke", metrics)

    asyncio.run(scenario())
