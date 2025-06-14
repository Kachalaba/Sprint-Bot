from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


def parse_time(t: str) -> float:
    """Parse a time string to seconds."""
    t = t.strip().replace(",", ".")
    if ":" in t:
        m, s = t.split(":", 1)
        return int(m) * 60 + float(s)
    return float(t)


def fmt_time(sec: float) -> str:
    """Format seconds to string m:ss.ss."""
    m, s = divmod(sec, 60)
    return f"{int(m)}:{s:05.2f}" if m else f"{s:0.2f}"


def speed(dist: float, sec: float) -> float:
    """Return speed in meters per second."""
    return dist / sec if sec else 0.0


def get_segments(dist: int) -> list[float]:
    """Split a distance into segments."""
    if dist == 50:
        return [12.5, 12.5, 0, 12.5, 12.5]
    if dist == 100:
        return [25, 25, 25, 25]
    if dist == 200:
        return [50, 50, 50, 50]
    if dist >= 400:
        segs = [50] + [100] * ((dist - 50) // 100)
        rest = dist - sum(segs)
        if rest:
            segs.append(rest)
        return segs
    raise ValueError("unsupported distance")


def pr_key(uid: int, stroke: str, dist: int, idx: int) -> str:
    """Generate a key for personal records."""
    return f"{uid}|{stroke}|{dist}|{idx}"


class AddResult(StatesGroup):
    """States for adding sprint results."""

    choose_athlete = State()
    choose_dist = State()
    collect = State()
