"""Dark Theater + Same-Seq — render rules, not a new lobe.

LIVE paints only a current FrameHub frame. Last-good BGR is a bug.
Widgets (situation / lockbug / controller) paint only when
``widget.frame_seq == live.frame_seq``. Plane Dim sleeps the board on menu/pause.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

OVERLAY_STATES = frozenset({"menu", "lobby", "hub", "paused", "pause"})
GAMEPLAY_STATES = frozenset({"gameplay", "playing", "in_game", "replay", "spectating"})
BLANK_LUMA_STD = 1.0


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


def is_play_state(game_state: str | None, hysteresis: str | None) -> bool:
    """Title-presence play vs menu/pause. Missing optics do not force dark."""
    gs = str(game_state or "").lower().strip()
    hyst = str(hysteresis or "").lower().strip()
    if gs in OVERLAY_STATES:
        return False
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
) -> LivePaint:
    """Single gate for Theater LIVE + widget ghosting.

    Reasons: ``ok`` | ``no_frame`` | ``blank`` | ``not_play`` | ``seq_skew``.
    Seq-skewed and blank LIVE go dark — never last-good BGR.
    """
    live_seq = int(live_seq or 0)
    wseq = int(widget_seq or 0)
    plane_dim = not is_play_state(game_state, title_hysteresis)
    if not has_frame:
        return LivePaint(False, live_seq, wseq, False, True, "no_frame", False)
    if blank is None:
        blank = is_blank_bgr(frame) if frame is not None else False
    if blank:
        return LivePaint(False, live_seq, wseq, False, True, "blank", True)
    if plane_dim:
        return LivePaint(False, live_seq, wseq, False, True, "not_play", True)
    same = live_seq > 0 and wseq == live_seq
    if not same:
        return LivePaint(False, live_seq, wseq, False, False, "seq_skew", True)
    return LivePaint(True, live_seq, wseq, True, False, "ok", True)


def snapshot_live_paint(situation: dict[str, Any] | None = None) -> LivePaint:
    """Live decision from FrameHub + Deck situation. Never opens capture."""
    sit = situation if isinstance(situation, dict) else {}
    has_frame = False
    live_seq = 0
    frame = None
    try:
        from qoresence.monitor.frame_hub import get_frame_hub, get_latest

        st = get_frame_hub().get_latest_stamp()
        has_frame = bool(st.get("has_frame"))
        live_seq = int(st.get("seq") or 0)
        if has_frame:
            frame = get_latest()
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
        frame=frame,
    )
