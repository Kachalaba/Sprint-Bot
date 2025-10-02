"""Helpers for quick result entry translations."""

from __future__ import annotations

from i18n import t
from utils import fmt_time, speed


def build_quick_prompt(idx: int, length: float) -> str:
    """Return localized prompt for collecting a segment time."""

    distance = f"{length:g}"
    prompt = t("add.quick.prompt", idx=idx + 1, distance=distance)
    example = t("add.quick.example")
    return f"{prompt}\n{example}"


def build_quick_saved(dist: int, total: float) -> str:
    """Return localized summary header for a saved result."""

    return t(
        "add.quick.saved",
        total=fmt_time(total),
        speed=f"{speed(dist, total):.2f}",
    )


__all__ = ["build_quick_prompt", "build_quick_saved"]
