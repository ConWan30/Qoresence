"""Pure flag heuristics for the pilot monitor. No I/O, no capture."""

from __future__ import annotations

from typing import Any

AGE_FREEZE_S = 5.0
FREEZE_STREAK = 3
NO_FRAME_STREAK = 5
UNLOCKED_S = 120.0
GRAPH_TIMEOUT_S = 2.0
WARM_UP_S = 30.0


def score_pair(home: Any, away: Any) -> tuple[int, int] | None:
    try:
        if home is None or away is None:
            return None
        return (int(home), int(away))
    except (TypeError, ValueError):
        return None


def score_changed(
    prev: tuple[int, int] | None, cur: tuple[int, int] | None
) -> bool:
    if prev is None or cur is None:
        return False
    return prev != cur


def score_decreased(
    prev: tuple[int, int] | None, cur: tuple[int, int] | None
) -> bool:
    """Football scores only go up in a game. A drop is flicker, not a clip."""
    if prev is None or cur is None:
        return False
    return cur[0] < prev[0] or cur[1] < prev[1]


def freeze_streak(has_frame: bool, age_s: float | None, streak: int) -> int:
    if has_frame and age_s is not None:
        try:
            if float(age_s) > AGE_FREEZE_S:
                return streak + 1
        except (TypeError, ValueError):
            return 0
    return 0


def freeze_flag(streak: int) -> bool:
    return streak >= FREEZE_STREAK


def no_frame_streak(has_frame: bool, frames: int | None, streak: int) -> int:
    empty = (not has_frame) or frames == 0 or frames is None
    return streak + 1 if empty else 0


def no_frame_flag(streak: int, elapsed_s: float, warm_up_s: float = WARM_UP_S) -> bool:
    return elapsed_s >= warm_up_s and streak >= NO_FRAME_STREAK


def unlocked_tick(
    has_scores: bool, locked: bool | None, unlocked_s: float, interval_s: float
) -> float:
    if has_scores and locked is False:
        return unlocked_s + interval_s
    return 0.0


def unlocked_flag(unlocked_s: float) -> bool:
    return unlocked_s > UNLOCKED_S
