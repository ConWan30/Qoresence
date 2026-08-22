"""Play-phrase lattice — typed DualSense ↔ video co-occurrence.

Observation plane only. Closed vocab, deterministic rules, no LLM.
``THROW`` is forbidden (authorship). ``RELEASE`` is the observation word.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

PHRASES = ("IDLE", "HUDDLE", "SNAP", "SPRINT", "CUT", "RELEASE")
# DELETED: play-phrase lattice disabled (operator ConWan30 — Theater LIVE).
# Env re-enable removed; classify_phrase is a hard no-op.
PLAY_PHRASE_ENABLED = False
LIVE_PHRASES = frozenset({"SNAP", "SPRINT", "CUT", "RELEASE"})

R2_FLOOR = 0.08
STICK_FLOOR = 0.15
MOTION_FLOOR = 1.2
# At 6fps capture (stressed USB card), frames are ~167ms apart — the old
# 0.20s threshold made every frame stale and forced phrase=IDLE even during
# active gameplay. 0.35s tolerates 6fps with jitter margin.
STALE_VIDEO_S = 0.35
# Soft-floor DualSense chatter dwell before accepting a new phrase.
DWELL_NS = 500_000_000  # 500 ms
DWELL_SAMPLES = 6

_MENU = frozenset({"menu", "lobby", "hub", "paused", "pause"})
_PLAY = frozenset({"gameplay", "playing", "in_game"})

_lock = threading.Lock()
_game_state = ""
_last_phrase: str | None = None
_last_conf: float = 0.0
_last_change_ns: int = 0
_candidate: str | None = None
_candidate_since_ns: int = 0
_candidate_count: int = 0


def note_game_state(state: str | None) -> None:
    """Situation / visual lobe writes the latest game_state for the classifier."""
    global _game_state
    with _lock:
        _game_state = str(state or "").strip().lower()


def current_game_state() -> str:
    with _lock:
        return _game_state


def reset_phrase_sticky() -> None:
    """Clear sticky dwell (tests / session restart)."""
    global _last_phrase, _last_conf, _last_change_ns
    global _candidate, _candidate_since_ns, _candidate_count
    with _lock:
        _last_phrase = None
        _last_conf = 0.0
        _last_change_ns = 0
        _candidate = None
        _candidate_since_ns = 0
        _candidate_count = 0


def _raw_classify_phrase(
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
    """Instantaneous classifier (no dwell). Fail-closed to IDLE."""
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


def _accept(phrase: str, conf: float, now: int) -> tuple[str, float]:
    global _last_phrase, _last_conf, _last_change_ns
    global _candidate, _candidate_since_ns, _candidate_count
    _last_phrase = phrase
    _last_conf = conf
    _last_change_ns = now
    _candidate = None
    _candidate_since_ns = 0
    _candidate_count = 0
    return phrase, conf


def _apply_sticky(
    raw: str,
    conf: float,
    *,
    r2: float,
    prev_r2: float,
    r2_onset_edge: bool,
    now_ns: int | None,
) -> tuple[str, float]:
    """Hold last_phrase across DualSense soft-floor chatter."""
    global _last_phrase, _last_conf, _last_change_ns
    global _candidate, _candidate_since_ns, _candidate_count

    now = int(now_ns) if now_ns is not None else time.monotonic_ns()
    r2 = max(0.0, float(r2))
    prev = max(0.0, float(prev_r2))
    onset = bool(r2_onset_edge) or (prev < R2_FLOOR <= r2)
    release = prev >= R2_FLOOR > r2
    # Soft-floor USB chatter crosses R2_FLOOR constantly; only a clear drop
    # (prev well above floor) is a hard RELEASE edge.
    hard_release = release and raw == "RELEASE" and prev >= max(0.25, 3.0 * R2_FLOOR)
    hard_snap = onset and raw == "SNAP"
    hard_edge = hard_release or hard_snap

    with _lock:
        if _last_phrase is None:
            return _accept(raw, conf, now)

        if raw == _last_phrase:
            _last_conf = conf
            _candidate = None
            _candidate_since_ns = 0
            _candidate_count = 0
            return _last_phrase, conf

        if hard_edge:
            return _accept(raw, conf, now)

        # Never demote LIVE → HUDDLE/IDLE on one quiet sample (dwell required).
        demote = _last_phrase in LIVE_PHRASES and raw in {"HUDDLE", "IDLE"}

        if _candidate != raw:
            _candidate = raw
            _candidate_since_ns = now
            _candidate_count = 1
        else:
            _candidate_count += 1

        # Soft transitions need BOTH sample count and wall time so a fast
        # controller poll cannot clear dwell in ~30ms via samples alone.
        # Demotions LIVE→HUDDLE/IDLE keep the same bar (never one quiet sample).
        need_samples = DWELL_SAMPLES + (2 if demote else 0)
        need_ns = DWELL_NS + (200_000_000 if demote else 0)
        sustained = (
            _candidate_count >= need_samples
            and (now - _candidate_since_ns) >= need_ns
        )
        if sustained:
            return _accept(raw, conf, now)

        return _last_phrase, _last_conf


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
    now_ns: int | None = None,
) -> tuple[str, float]:
    """DELETED play-phrase lattice — always OFF; ignore DualSense/video_age."""
    return "OFF", 0.0


def phrase_payload(phrase: str, confidence: float) -> dict[str, Any]:
    """DELETED — fixed disabled payload (no LIVE licensing)."""
    return {"phrase": "OFF", "phrase_conf": 0.0, "phrase_live": False}
