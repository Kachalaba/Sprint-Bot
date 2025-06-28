from __future__ import annotations

import re
from datetime import datetime, timezone

from aiogram.fsm.state import State, StatesGroup

# --- FSM States ---
class AddResult(StatesGroup):
    choose_dist = State()
    waiting_for_stroke = State()
    collect = State()
    choose_athlete = State()

# --- Utility Functions ---

def parse_time(s: str) -> float:
    """Parse time from string like 1:23.45 or 23.45 into seconds."""
    if ":" in s:
        m, s = s.split(":")
        return int(m) * 60 + float(s)
    return float(s)

def fmt_time(seconds: float) -> str:
    """Format seconds into a string like 1:23.45."""
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:05.2f}" if m else f"{s:.2f}"

def get_segments(dist: int) -> list[int]:
    """
    Рассчитывает правильные отрезки для анализа дистанции.
    - 50м: делится на 4 отрезка по 12.5м.
    - 100м: делится на 4 отрезка по 25м.
    - 200м и более: делится на отрезки по 50м.
    """
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
