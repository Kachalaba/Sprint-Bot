"""Shared utilities for Sprint Bot."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup

from .parse_time import parse_splits, parse_total, validate_splits

__all__ = [
    "AddResult",
    "TemplateStates",
    "fmt_time",
    "get_segments",
    "parse_splits",
    "parse_total",
    "pr_key",
    "speed",
    "validate_splits",
]


# --- FSM States ---
class AddResult(StatesGroup):
    """Finite state machine for manual result entry."""

    choose_dist = State()
    waiting_for_stroke = State()
    collect = State()
    choose_athlete = State()
    waiting_for_comment = State()
    editing_comment = State()


class TemplateStates(StatesGroup):
    """FSM states for sprint template management."""

    menu = State()
    create_title = State()
    create_distance = State()
    create_stroke = State()
    create_segments = State()
    create_hint = State()
    editing_value = State()
    editing_stroke = State()


# --- Utility Functions ---


def fmt_time(seconds: float) -> str:
    """Format seconds into a string like 1:23.45."""

    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:05.2f}" if m else f"{s:.2f}"


def get_segments(dist: int) -> list[int]:
    """Calculate segment lengths for sprint analysis."""

    if dist == 50:
        # 50м - это 4 сегмента по 12.5м для детального анализа
        return [12.5, 12.5, 12.5, 12.5]
    if dist == 100:
        # Сотка - это классические 4 по 25м
        return [25, 25, 25, 25]
    if dist >= 200:
        # 200м и длиннее - анализируем по "полтинникам"
        num_segments = dist // 50
        return [50] * num_segments

    # На случай, если дистанция не стандартная (например, 75м)
    return [dist]


def pr_key(uid: int, stroke: str, dist: int, seg_idx: int) -> str:
    """Generate a unique key for a personal record."""

    return f"{uid}|{stroke}|{dist}|{seg_idx}"


def speed(dist: float, time: float) -> float:
    """Calculate speed in m/s."""

    if not time:
        return 0
    return dist / time


def parse_time(value: str) -> float:
    """Backward compatible alias for :func:`parse_total`."""

    return parse_total(value)
