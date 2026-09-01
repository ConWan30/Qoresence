"""Dark Theater + Same-Seq — render rules, not a new lobe.

LIVE paints only a current FrameHub frame. Last-good BGR is a bug.
Widgets (situation / lockbug / controller) paint when
``|widget.frame_seq - live.frame_seq| <= SAME_SEQ_SLACK``. Plane Dim sleeps the board on menu/pause.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

OVERLAY_STATES = frozenset({"menu", "lobby", "hub", "paused", "pause"})
GAMEPLAY_STATES = frozenset({"gameplay", "playing", "in_game", "replay", "spectating"})
BLANK_LUMA_STD = 1.0
# Situation updates slower than the 30 fps hub. Exact seq match blacks the
# picture and ghosts a live VLM lock. ~0.4s slack keeps Same-Seq honest.
SAME_SEQ_SLACK = 12


@dataclass(frozen=True)
class LivePaint:
    paint: bool
    live_seq: int
    widget_seq: int
    same_seq: bool
    plane_dim: bool
    reason: str
    has_frame: bool

    def widgets_ok(self) -> bool:
        """Scorebug/controller: same seq, not dimmed, LIVE actually painting."""
        return self.paint and self.same_seq and not self.plane_dim


def is_blank_bgr(frame: Any) -> bool:
    """Uniform / empty frame — no scoreboard, no LIVE picture."""
    if frame is None:
        return True
    try:
        import numpy as np

        arr = np.asarray(frame)
        if arr.size == 0:
            return True
        if arr.ndim == 3 and arr.shape[2] >= 3:
            gray = arr.mean(axis=2)
        else:
            gray = arr
        return float(gray.std()) < BLANK_LUMA_STD
    except Exception:
        return False


def _locked_board_live(
    *,
    locked: bool,
    quarter: Any = None,
    down: Any = None,
    home_score: Any = None,
    away_score: Any = None,
) -> bool:
    """Locked scorebug is live with quarter/down OR a home+away pair."""
    if not locked:
        return False
    if quarter is not None or down is not None:
        return True
    return home_score is not None and away_score is not None


def is_play_state(
    game_state: str | None,
    hysteresis: str | None,
    *,
    locked: bool = False,
    quarter: Any = None,
    down: Any = None,
    home_score: Any = None,
    away_score: Any = None,
) -> bool:
    """Title-presence play vs menu/pause. Missing optics do not force dark.

    Locked scorebug stays play even when title hysteresis is ``overlay`` /
    ``overlay-rejected``, including menu/huddle mislabels (cfb27 effective_game_state
    intent). Real pause without treating locked digits as huddle still dims;
    menu/lobby with locked digits lights the board.
    """
    gs = str(game_state or "").lower().strip()
    hyst = str(hysteresis or "").lower().strip()
    locked_board = _locked_board_live(
        locked=bool(locked),
        quarter=quarter,
        down=down,
        home_score=home_score,
        away_score=away_score,
    )
    # Pause is always overlay. Menu/lobby/hub with a locked board → gameplay.
    if gs in {"paused", "pause"}:
        return False
    if locked_board and gs in {"menu", "lobby", "hub", "unknown", ""}:
        gs = "gameplay"
    elif gs in OVERLAY_STATES:
        return False
    if locked_board and gs in GAMEPLAY_STATES:
        return True
    if hyst in ("overlay-rejected", "overlay"):
        return False
    if gs in GAMEPLAY_STATES or hyst == "locked":
        return True
    if not gs and not hyst:
        return True
    if hyst in ("unknown", "transitioning"):
        return False
    return True


def decide_live_paint(
    *,
    has_frame: bool,
    live_seq: int = 0,
    widget_seq: int | None = 0,
    game_state: str | None = None,
    title_hysteresis: str | None = None,
    frame: Any = None,
    blank: bool | None = None,
    score_vlm_locked: bool | None = None,
    scoreboard_locked: bool | None = None,
    quarter: Any = None,
    down: Any = None,
    home_score: Any = None,
    away_score: Any = None,
) -> LivePaint:
    """Single gate for Theater LIVE + widget ghosting.

    Reasons: ``ok`` | ``no_frame`` | ``blank`` | ``not_play`` | ``seq_skew``.
    Missing / blank / not-play LIVE go dark — never last-good BGR.
    Seq skew ghosts widgets only; the current hub frame still paints.
    """
    live_seq = int(live_seq or 0)
    wseq = int(widget_seq or 0)
    locked = bool(score_vlm_locked) or bool(scoreboard_locked)
    plane_dim = not is_play_state(
        game_state,
        title_hysteresis,
        locked=locked,
        quarter=quarter,
        down=down,
        home_score=home_score,
        away_score=away_score,
    )
    if not has_frame:
        paint = LivePaint(False, live_seq, wseq, False, True, "no_frame", False)
        _note_same_seq(paint)
        _note_absence("no_frame")
        return paint
    if blank is None:
        blank = is_blank_bgr(frame) if frame is not None else False
    if blank:
        paint = LivePaint(False, live_seq, wseq, False, True, "blank", True)
        _note_same_seq(paint)
        _note_absence("blank")
        return paint
    if plane_dim:
        paint = LivePaint(False, live_seq, wseq, False, True, "not_play", True)
        _note_same_seq(paint)
        return paint
    same = live_seq > 0 and (wseq == live_seq or abs(live_seq - wseq) <= SAME_SEQ_SLACK)
    if not same:
        paint = LivePaint(True, live_seq, wseq, False, False, "seq_skew", True)
    else:
        paint = LivePaint(True, live_seq, wseq, True, False, "ok", True)
    _note_same_seq(paint)
    return paint


def _note_same_seq(paint: LivePaint) -> None:
    try:
        from qoresence.graphs.same_seq_join import record_live_paint

        record_live_paint(paint)
    except Exception:
        pass


def _note_absence(kind: str) -> None:
    try:
        from qoresence.graphs.negative_evidence import record_absence

        record_absence(kind)
    except Exception:
        pass


def snapshot_live_paint(situation: dict[str, Any] | None = None) -> LivePaint:
    """Live decision from FrameHub + Deck situation. Never opens capture."""
    sit = situation if isinstance(situation, dict) else {}
    has_frame = False
    live_seq = 0
    stamp_blank: bool | None = None
    try:
        from qoresence.monitor.frame_hub import get_frame_hub

        st = get_frame_hub().get_latest_stamp()
        has_frame = bool(st.get("has_frame"))
        live_seq = int(st.get("seq") or 0)
        if "blank" in st:
            stamp_blank = bool(st.get("blank"))
    except Exception:
        pass
    widget_seq = sit.get("frame_seq")
    if widget_seq is None:
        widget_seq = sit.get("seq")
    try:
        widget_seq = int(widget_seq or 0)
    except (TypeError, ValueError):
        widget_seq = 0
    if widget_seq <= 0:
        widget_seq = live_seq
    gs = sit.get("game_state")
    if hasattr(gs, "value"):
        gs = gs.value
    hyst = sit.get("title_hysteresis") or sit.get("hysteresis")
    return decide_live_paint(
        has_frame=has_frame,
        live_seq=live_seq,
        widget_seq=widget_seq,
        game_state=str(gs) if gs is not None else None,
        title_hysteresis=str(hyst) if hyst is not None else None,
        blank=stamp_blank,
        score_vlm_locked=sit.get("score_vlm_locked"),
        scoreboard_locked=sit.get("scoreboard_locked"),
        quarter=sit.get("quarter"),
        down=sit.get("down"),
        home_score=sit.get("home_score", sit.get("score_home")),
        away_score=sit.get("away_score", sit.get("score_away")),
    )
