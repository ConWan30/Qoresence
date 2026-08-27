"""Ghost Stick — DualSense locus delayed onto the HDMI frame it belongs to.

Observation plane only. Opt-in, default OFF. Subscribes FrameHub stamps +
InputRing analog poses + IVC lag. Never opens capture. Never interpolates a
silent pad. Last-good pose is not painted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from qoresence.sync.input_ring import DEFAULT_HOLD_FRESH_MS, AnalogPose

COUPLING_FLOOR = 0.12
DEFAULT_LAG_MS = 80.0
IDLE_STICK = 0.15
IDLE_TRIGGER = 0.08

_enabled = False


def set_ghost_stick_enabled(on: bool) -> None:
    global _enabled
    _enabled = bool(on)


def ghost_stick_enabled() -> bool:
    env = os.environ.get("QORESENCE_GHOST_STICK", "").strip().lower()
    if env in {"0", "false", "no", "off"}:
        return False
    if env in {"1", "true", "yes", "on"}:
        return True
    return True


@dataclass(frozen=True)
class GhostStickView:
    enabled: bool
    paint: bool
    lx: float
    ly: float
    r2: float
    l2: float
    lag_ms: float
    frame_seq: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "paint": self.paint,
            "lx": round(float(self.lx), 3),
            "ly": round(float(self.ly), 3),
            "r2": round(float(self.r2), 3),
            "l2": round(float(self.l2), 3),
            "lag_ms": round(float(self.lag_ms), 1),
            "frame_seq": int(self.frame_seq),
            "reason": self.reason,
        }


def _idle(pose: AnalogPose) -> bool:
    mag = (float(pose.lx) ** 2 + float(pose.ly) ** 2) ** 0.5
    return mag < IDLE_STICK and pose.r2 < IDLE_TRIGGER and pose.l2 < IDLE_TRIGGER


def _off(*, enabled: bool, reason: str, lag_ms: float, frame_seq: int) -> GhostStickView:
    return GhostStickView(
        enabled=enabled,
        paint=False,
        lx=0.0,
        ly=0.0,
        r2=0.0,
        l2=0.0,
        lag_ms=lag_ms,
        frame_seq=frame_seq,
        reason=reason,
    )


def decide_ghost_stick(
    *,
    enabled: bool,
    paint_reason: str,
    same_seq: bool,
    plane_dim: bool,
    live_seq: int,
    widget_seq: int,
    coupling: float,
    pose: AnalogPose | None,
    lag_ms: float,
) -> GhostStickView:
    """Pure gate. Tests lock delay / vanish / Same-Seq here.

    Reasons: ``off`` | ``ok`` | ``idle`` | ``coupling`` | ``seq_skew`` |
    ``not_play`` | ``no_frame`` | ``blank``.
    """
    lag = float(lag_ms)
    seq = int(live_seq or 0)
    if not enabled:
        return _off(enabled=False, reason="off", lag_ms=lag, frame_seq=seq)
    reason = str(paint_reason or "")
    if plane_dim or reason == "not_play":
        return _off(enabled=True, reason="not_play", lag_ms=lag, frame_seq=seq)
    if reason in ("no_frame", "blank"):
        return _off(enabled=True, reason=reason, lag_ms=lag, frame_seq=seq)
    if reason == "seq_skew" or not same_seq or (seq > 0 and int(widget_seq or 0) != seq):
        return _off(enabled=True, reason="seq_skew", lag_ms=lag, frame_seq=seq)
    if pose is None or _idle(pose):
        return _off(enabled=True, reason="idle", lag_ms=lag, frame_seq=seq)
    if float(coupling) < COUPLING_FLOOR:
        return _off(enabled=True, reason="coupling", lag_ms=lag, frame_seq=seq)
    return GhostStickView(
        enabled=True,
        paint=True,
        lx=float(pose.lx),
        ly=float(pose.ly),
        r2=float(pose.r2),
        l2=float(pose.l2),
        lag_ms=lag,
        frame_seq=seq,
        reason="ok",
    )


def _lag_ms(coupling: dict[str, Any]) -> float:
    center = coupling.get("lag_center_ms")
    try:
        if center is not None:
            return max(0.0, float(center))
    except (TypeError, ValueError):
        pass
    band = coupling.get("lag_band_ms")
    if isinstance(band, (list, tuple)) and len(band) >= 2:
        try:
            return max(0.0, (float(band[0]) + float(band[1])) / 2.0)
        except (TypeError, ValueError):
            pass
    return DEFAULT_LAG_MS


def snapshot_ghost_stick(
    *,
    live_paint: Any | None = None,
    situation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cheap read of IVC + hid_by_seq. Never copies BGR. Never emits bus events."""
    on = ghost_stick_enabled()
    paint_reason = "no_frame"
    same_seq = False
    plane_dim = True
    live_seq = 0
    widget_seq = 0
    if live_paint is not None:
        paint_reason = str(getattr(live_paint, "reason", "") or "")
        same_seq = bool(getattr(live_paint, "same_seq", False))
        plane_dim = bool(getattr(live_paint, "plane_dim", False))
        live_seq = int(getattr(live_paint, "live_seq", 0) or 0)
        widget_seq = int(getattr(live_paint, "widget_seq", 0) or 0)
    sit = situation if isinstance(situation, dict) else {}
    if widget_seq <= 0:
        try:
            widget_seq = int(sit.get("frame_seq") or 0)
        except (TypeError, ValueError):
            widget_seq = 0

    coupling_payload: dict[str, Any] = {}
    try:
        from qoresence.sync.ivc import get_last_coupling

        coupling_payload = get_last_coupling() or {}
    except Exception:
        coupling_payload = {}
    coupling = float(coupling_payload.get("coupling") or coupling_payload.get("coupling_ema") or 0.0)
    lag = _lag_ms(coupling_payload)
    if live_seq <= 0:
        try:
            live_seq = int(coupling_payload.get("frame_seq") or 0)
        except (TypeError, ValueError):
            live_seq = 0

    # Read HID from delay line by seq, not HID[now]
    pose = None
    if on and live_seq > 0:
        try:
            from qoresence.sync.hid_seq_line import get_sample

            sample = get_sample(live_seq)
            if sample is not None:
                # Convert HidSeqSample to AnalogPose for decide_ghost_stick
                pose = AnalogPose(
                    clock_ns=sample.hid_clock_ns,
                    lx=sample.lx,
                    ly=sample.ly,
                    r2=sample.r2,
                    l2=sample.l2,
                )
        except Exception:
            pose = None

    view = decide_ghost_stick(
        enabled=on,
        paint_reason=paint_reason,
        same_seq=same_seq,
        plane_dim=plane_dim,
        live_seq=live_seq,
        widget_seq=widget_seq,
        coupling=coupling,
        pose=pose,
        lag_ms=lag,
    )
    return view.to_dict()
