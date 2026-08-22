"""Thread-safe ring of recent controller input edges (observation plane).

Joins HID press/release/trigger/stick edges to video by wall-clock window
(shared ``clock_ns`` / monotonic_ns). Also keeps a throttled analog *hold*
snapshot so sprint / stick sustain still couple after the onset edge ages
out of the IVC lag band. Does not open capture devices.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# ~5 s at high event rate (edges only; not 1 kHz full state)
DEFAULT_CAPACITY = 4096
DEFAULT_MAX_AGE_S = 5.0
# Hold is "live" only while HID is still writing (controller throttles ~60 Hz)
DEFAULT_HOLD_FRESH_MS = 80.0
# ~3 s of analog poses at 60 Hz — Ghost Stick samples by delayed clock_ns
_POSE_CAP = 180

# Energy weights for simple activity score
_WEIGHT = {
    "press": 1.0,
    "release": 0.15,
    "trigger": 1.2,
    "stick": 0.4,
}

# Sustain weights — analog holds (CFB sprint / steer) after the edge expires
_HOLD_WEIGHT = {
    "r2": 1.35,
    "l2": 1.15,
    "left": 0.45,
    "right": 0.50,
    "button": 0.35,
}
_HOLD_TRIGGER_FLOOR = 0.08
_HOLD_STICK_FLOOR = 0.15


@dataclass
class InputEvent:
    """One input edge for ring storage / clip sidecar."""

    clock_ns: int
    kind: str  # "press" | "release" | "trigger" | "stick"
    name: str
    value: float = 1.0
    buttons_mask: int | None = None
    frame_seq: int | None = None
    imu_precursor_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Drop nulls for compact sidecars
        return {k: v for k, v in d.items() if v is not None}


@dataclass(frozen=True)
class AnalogPose:
    """One analog sample for Ghost Stick (lx/ly are -1..+1, +ly is down)."""

    clock_ns: int
    lx: float = 0.0
    ly: float = 0.0
    r2: float = 0.0
    l2: float = 0.0


@dataclass
class HoldState:
    """Latest analog / digital hold (not an edge). clock_ns = last HID write."""

    clock_ns: int = 0
    r2: float = 0.0
    l2: float = 0.0
    left: float = 0.0
    right: float = 0.0
    buttons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clock_ns": int(self.clock_ns),
            "r2": round(float(self.r2), 3),
            "l2": round(float(self.l2), 3),
            "left": round(float(self.left), 3),
            "right": round(float(self.right), 3),
            "buttons": list(self.buttons),
        }


class InputRing:
    """Thread-safe deque of recent InputEvents, keyed by clock_ns."""

    def __init__(
        self,
        capacity: int = DEFAULT_CAPACITY,
        max_age_s: float = DEFAULT_MAX_AGE_S,
    ) -> None:
        self._capacity = max(16, int(capacity))
        self._max_age_ns = int(float(max_age_s) * 1e9)
        self._lock = threading.Lock()
        self._events: deque[InputEvent] = deque(maxlen=self._capacity)
        self._latest_buttons: list[str] = []
        self._hold = HoldState()
        self._poses: deque[AnalogPose] = deque(maxlen=_POSE_CAP)

    def push(self, ev: InputEvent | dict[str, Any]) -> None:
        """Append an edge. Never raises into HID poll loop."""
        try:
            if isinstance(ev, dict):
                ev = InputEvent(
                    clock_ns=int(ev.get("clock_ns") or time.monotonic_ns()),
                    kind=str(ev.get("kind") or "press"),
                    name=str(ev.get("name") or "?"),
                    value=float(ev.get("value", 1.0)),
                    buttons_mask=ev.get("buttons_mask"),
                    frame_seq=ev.get("frame_seq"),
                    imu_precursor_ms=ev.get("imu_precursor_ms"),
                )
            if ev.clock_ns <= 0:
                ev.clock_ns = time.monotonic_ns()
            with self._lock:
                self._events.append(ev)
                if ev.kind == "press" and ev.name:
                    if ev.name not in self._latest_buttons:
                        self._latest_buttons.append(ev.name)
                        if len(self._latest_buttons) > 16:
                            self._latest_buttons = self._latest_buttons[-16:]
                elif ev.kind == "release" and ev.name in self._latest_buttons:
                    self._latest_buttons = [b for b in self._latest_buttons if b != ev.name]
                self._prune_locked(time.monotonic_ns())
        except Exception as e:
            log.debug("InputRing.push failed: %s", e)

    def set_hold(
        self,
        *,
        clock_ns: int,
        r2: float = 0.0,
        l2: float = 0.0,
        left: float = 0.0,
        right: float = 0.0,
        buttons: list[str] | tuple[str, ...] | None = None,
        lx: float = 0.0,
        ly: float = 0.0,
    ) -> None:
        """Overwrite analog hold. Never raises into HID poll loop."""
        try:
            ts = int(clock_ns) if clock_ns and int(clock_ns) > 0 else time.monotonic_ns()
            btns = tuple(str(b) for b in buttons) if buttons is not None else None
            r2_c = max(0.0, min(1.5, float(r2)))
            l2_c = max(0.0, min(1.5, float(l2)))
            lx_c = max(-1.0, min(1.0, float(lx)))
            ly_c = max(-1.0, min(1.0, float(ly)))
            with self._lock:
                self._hold = HoldState(
                    clock_ns=ts,
                    r2=r2_c,
                    l2=l2_c,
                    left=max(0.0, min(1.5, float(left))),
                    right=max(0.0, min(1.5, float(right))),
                    buttons=btns if btns is not None else tuple(self._latest_buttons[:8]),
                )
                self._poses.append(AnalogPose(clock_ns=ts, lx=lx_c, ly=ly_c, r2=r2_c, l2=l2_c))
        except Exception as e:
            log.debug("InputRing.set_hold failed: %s", e)

    def pose_at(self, clock_ns: int, max_age_ms: float = DEFAULT_HOLD_FRESH_MS) -> AnalogPose | None:
        """Latest pose with clock_ns <= target. None if missing or stale — no interpolate."""
        target = int(clock_ns)
        max_age_ns = int(max(1.0, float(max_age_ms)) * 1e6)
        with self._lock:
            best: AnalogPose | None = None
            for p in self._poses:
                if p.clock_ns <= target:
                    best = p
                else:
                    break
            if best is None:
                return None
            if target - best.clock_ns > max_age_ns:
                return None
            return best

    def hold(self) -> HoldState:
        with self._lock:
            return HoldState(
                clock_ns=self._hold.clock_ns,
                r2=self._hold.r2,
                l2=self._hold.l2,
                left=self._hold.left,
                right=self._hold.right,
                buttons=self._hold.buttons,
            )

    def hold_energy(
        self,
        now_ns: int | None = None,
        max_age_ms: float = DEFAULT_HOLD_FRESH_MS,
    ) -> float:
        """Weighted sustain from the live analog hold. 0 if stale or idle."""
        now = int(now_ns) if now_ns is not None else time.monotonic_ns()
        max_age_ns = int(max(1.0, float(max_age_ms)) * 1e6)
        with self._lock:
            h = self._hold
            if h.clock_ns <= 0:
                return 0.0
            age = now - h.clock_ns
            if age < 0 or age > max_age_ns:
                return 0.0
            energy = 0.0
            if h.r2 >= _HOLD_TRIGGER_FLOOR:
                energy += _HOLD_WEIGHT["r2"] * min(1.0, h.r2)
            if h.l2 >= _HOLD_TRIGGER_FLOOR:
                energy += _HOLD_WEIGHT["l2"] * min(1.0, h.l2)
            if h.left >= _HOLD_STICK_FLOOR:
                energy += _HOLD_WEIGHT["left"] * min(1.0, h.left)
            if h.right >= _HOLD_STICK_FLOOR:
                energy += _HOLD_WEIGHT["right"] * min(1.0, h.right)
            if h.buttons:
                energy += _HOLD_WEIGHT["button"] * min(3, len(h.buttons))
            return float(energy)

    def in_window(self, t0_ns: int, t1_ns: int) -> list[InputEvent]:
        """Events with clock_ns in [t0_ns, t1_ns] inclusive."""
        if t1_ns < t0_ns:
            t0_ns, t1_ns = t1_ns, t0_ns
        with self._lock:
            return [e for e in self._events if t0_ns <= e.clock_ns <= t1_ns]

    def energy(self, since_ns: int) -> float:
        """Weighted activity score for events with clock_ns >= since_ns."""
        with self._lock:
            total = 0.0
            for e in self._events:
                if e.clock_ns < since_ns:
                    continue
                w = _WEIGHT.get(e.kind, 0.5)
                total += w * min(1.5, abs(float(e.value)) + 0.25)
            return float(total)

    def latest_buttons(self) -> list[str]:
        with self._lock:
            return list(self._latest_buttons)

    def snapshot(self, seconds: float = 5.0) -> list[dict[str, Any]]:
        """Events in the last ``seconds`` for clip sidecar JSON."""
        now = time.monotonic_ns()
        since = now - int(max(0.05, float(seconds)) * 1e9)
        with self._lock:
            return [e.to_dict() for e in self._events if e.clock_ns >= since]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._latest_buttons.clear()
            self._hold = HoldState()
            self._poses.clear()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "count": len(self._events),
                "buttons": list(self._latest_buttons),
                "capacity": self._capacity,
                "hold": self._hold.to_dict(),
            }

    def _prune_locked(self, now_ns: int) -> None:
        cutoff = now_ns - self._max_age_ns
        while self._events and self._events[0].clock_ns < cutoff:
            self._events.popleft()


# Process-wide ring (controller + IVC + clip export share this process)
_ring = InputRing()
_ring_lock = threading.Lock()


def get_input_ring() -> InputRing:
    return _ring


def push(ev: InputEvent | dict[str, Any]) -> None:
    """Module helper — best-effort push for controller path."""
    try:
        get_input_ring().push(ev)
    except Exception:
        pass


def set_hold(
    *,
    clock_ns: int,
    r2: float = 0.0,
    l2: float = 0.0,
    left: float = 0.0,
    right: float = 0.0,
    buttons: list[str] | tuple[str, ...] | None = None,
    lx: float = 0.0,
    ly: float = 0.0,
) -> None:
    """Module helper — best-effort analog hold for controller path."""
    try:
        get_input_ring().set_hold(
            clock_ns=clock_ns,
            r2=r2,
            l2=l2,
            left=left,
            right=right,
            buttons=buttons,
            lx=lx,
            ly=ly,
        )
    except Exception:
        pass
