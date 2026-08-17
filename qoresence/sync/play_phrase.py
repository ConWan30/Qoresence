"""Play-phrase lattice — typed DualSense ↔ video co-occurrence.

Observation plane only. Closed vocab, deterministic rules, no LLM.
``THROW`` is forbidden (authorship). ``RELEASE`` is the observation word.
"""

from __future__ import annotations

import threading
from typing import Any

PHRASES = ("IDLE", "HUDDLE", "SNAP", "SPRINT", "CUT", "RELEASE")
LIVE_PHRASES = frozenset({"SNAP", "SPRINT", "CUT", "RELEASE"})

R2_FLOOR = 0.08
STICK_FLOOR = 0.15
MOTION_FLOOR = 1.2
# At 6fps capture (stressed USB card), frames are ~167ms apart — the old
# 0.20s threshold made every frame stale and forced phrase=IDLE even during
# active gameplay. 0.35s tolerates 6fps with jitter margin.
STALE_VIDEO_S = 0.35

_MENU = frozenset({"menu", "lobby", "hub", "paused", "pause"})
_PLAY = frozenset({"gameplay", "playing", "in_game"})

_lock = threading.Lock()
_game_state = ""


def note_game_state(state: str | None) -> None:
    """Situation / visual lobe writes the latest game_state for the classifier."""
    global _game_state
    with _lock:
        _game_state = str(state or "").strip().lower()


def current_game_state() -> str:
    with _lock:
        return _game_state


def classify_phrase(
    *,
    game_state: str | None = None,
    r2: float = 0.0,
    prev_r2: float = 0.0,
    left: float = 0.0,
    motion: float = 0.0,
    r2_onset_edge: bool = False,
    video_age_s: float = 0.0,
    hold_fresh: bool = False,
) -> tuple[str, float]:
    """Return (phrase, confidence). Fail-closed to IDLE."""
    gst = str(game_state if game_state is not None else current_game_state() or "").lower()
    r2 = max(0.0, float(r2))
    prev = max(0.0, float(prev_r2))
    left = max(0.0, float(left))
    motion = max(0.0, float(motion))
    age = max(0.0, float(video_age_s))
    onset = bool(r2_onset_edge) or (prev < R2_FLOOR <= r2)
    release = prev >= R2_FLOOR > r2
    stale = age > STALE_VIDEO_S
    menu = gst in _MENU
    play = gst in _PLAY

    if menu:
        return "IDLE", 0.95
    if stale and not onset and not release and r2 < R2_FLOOR:
        return "IDLE", 0.85

    if release:
        return "RELEASE", 0.80
    if onset and motion >= MOTION_FLOOR:
        return "SNAP", 0.75
    if r2 >= R2_FLOOR and hold_fresh and not stale:
        return "SPRINT", 0.70
    if left >= STICK_FLOOR and motion >= MOTION_FLOOR and not stale:
        return "CUT", 0.65
    if play and r2 < R2_FLOOR and left < STICK_FLOOR and not onset:
        return "HUDDLE", 0.60
    if r2 < R2_FLOOR and left < STICK_FLOOR and not onset and not release:
        return "IDLE", 0.80
    return "IDLE", 0.50


def phrase_payload(phrase: str, confidence: float) -> dict[str, Any]:
    p = str(phrase or "IDLE")
    if p not in PHRASES:
        p = "IDLE"
    return {
        "phrase": p,
        "phrase_conf": round(max(0.0, min(1.0, float(confidence))), 3),
        "phrase_live": p in LIVE_PHRASES,
    }
