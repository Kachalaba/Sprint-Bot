from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from sprint_bot.application.presenters import ProgressPresenter


@dataclass
class _Highlight:
    stroke: str
    distance: int
    total_seconds: float
    timestamp: datetime
    is_pr: bool


@dataclass
class _Progress:
    attempts: int
    pr_count: int
    highlights: Sequence[_Highlight] = field(default_factory=tuple)


def test_renders_empty_state_with_default_translator() -> None:
    rendered = ProgressPresenter().render(_Progress(attempts=0, pr_count=0))
    assert "No attempts" in rendered


def test_renders_highlights_with_pr_badge() -> None:
    view = _Progress(
        attempts=2,
        pr_count=1,
        highlights=(
            _Highlight(
                stroke="freestyle",
                distance=50,
                total_seconds=27.4,
                timestamp=datetime(2024, 5, 1, 18, 30),
                is_pr=True,
            ),
            _Highlight(
                stroke="backstroke",
                distance=100,
                total_seconds=70.5,
                timestamp=datetime(2024, 5, 3, 19, 0),
                is_pr=False,
            ),
        ),
    )

    rendered = ProgressPresenter().render(view)

    assert "2 attempts" in rendered
    assert "1 PR" in rendered
    assert "freestyle" in rendered
    assert "[PR]" in rendered
    assert "backstroke" in rendered


def test_uses_custom_translator_when_provided() -> None:
    captured: list[tuple[str, dict]] = []

    def translator(key, /, *, lang=None, **params):
        captured.append((key, dict(params, lang=lang)))
        return f"[{key}:{lang}]"

    view = _Progress(
        attempts=1,
        pr_count=0,
        highlights=(
            _Highlight(
                stroke="butterfly",
                distance=200,
                total_seconds=130.4,
                timestamp=datetime(2024, 6, 1),
                is_pr=False,
            ),
        ),
    )

    rendered = ProgressPresenter(translator=translator).render(view, lang="ru")

    assert "[presenter.progress.header:ru]" in rendered
    assert any(key.startswith("presenter.progress.highlight") for key, _ in captured)


def test_seconds_formatter_handles_minutes() -> None:
    presenter = ProgressPresenter()
    view = _Progress(
        attempts=1,
        pr_count=0,
        highlights=(
            _Highlight(
                stroke="freestyle",
                distance=400,
                total_seconds=265.4,
                timestamp=datetime(2024, 5, 1, 12, 0),
                is_pr=False,
            ),
        ),
    )
    rendered = presenter.render(view)
    assert "4:25.40" in rendered
