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


def get_segments(distance: int, split_length: int = 50) -> list[float]:
    """Return lengths of segments that make up the distance.

    The function splits the given ``distance`` into chunks of ``split_length``
    meters. All segments except the last one have the same length equal to
    ``split_length``. If the distance is not divisible by ``split_length``, the
    final segment will contain the remaining meters.

    Args:
        distance: Total distance of the swim in meters.
        split_length: Desired length of one segment in meters. Defaults to 50.

    Returns:
        A list of segment lengths in meters.
    """

    if distance <= 0:
        raise ValueError("distance must be positive")
    if split_length <= 0:
        raise ValueError("split_length must be positive")

    segments = [float(split_length)] * (distance // split_length)
    rest = distance % split_length
    if rest:
        segments.append(float(rest))
    return segments


def pr_key(uid: int, stroke: str, dist: int, idx: int) -> str:
    """Generate a key for personal records."""
    return f"{uid}|{stroke}|{dist}|{idx}"


class AddResult(StatesGroup):
    """States for adding sprint results."""

    choose_athlete = State()
    choose_dist = State()
    collect = State()
