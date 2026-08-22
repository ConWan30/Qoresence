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


def score_changed(prev: tuple[int, int] | None, cur: tuple[int, int] | None) -> bool:
    if prev is None or cur is None:
        return False
    return prev != cur


def score_decreased(prev: tuple[int, int] | None, cur: tuple[int, int] | None) -> bool:
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


FREEZE_KINDS = ("card_stall", "graph_stall", "deck_lock", "unknown")


def classify_freeze(
    *,
    has_frame: bool | None = None,
    age_s: float | None = None,
    frames: int | None = None,
    prev_frames: int | None = None,
    graph_stall: bool = False,
    deck_down: bool = False,
    health_err: bool = False,
    situation_timeout: bool = False,
) -> str:
    """Best-effort FREEZE owner. Fail soft — unknown is valid.

    card_stall: high video age and no frame progress.
    graph_stall: situation/timeline error while video looks healthy.
    deck_lock: health HTTP failed / DECK_DOWN.
    """
    if deck_down or health_err:
        return "deck_lock"
    age = None
    try:
        age = float(age_s) if age_s is not None else None
    except (TypeError, ValueError):
        age = None
    no_progress = False
    if prev_frames is not None and frames is not None:
        try:
            no_progress = int(frames) <= int(prev_frames)
        except (TypeError, ValueError):
            no_progress = False
    if (
        has_frame
        and age is not None
        and age > AGE_FREEZE_S
        and (no_progress or prev_frames is None)
    ):
        return "card_stall"
    if (graph_stall or situation_timeout) and (age is None or age < 1.5) and has_frame:
        return "graph_stall"
    if graph_stall or situation_timeout:
        return "graph_stall"
    return "unknown"


def freeze_owner(kind: str) -> str:
    return {
        "card_stall": "capture_card",
        "graph_stall": "situation_timeline",
        "deck_lock": "deck_http",
    }.get(str(kind or ""), "unknown")


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
