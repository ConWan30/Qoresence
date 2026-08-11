"""Thread-safe ring of recent controller input edges (observation plane).

Joins HID press/release/trigger/stick edges to video by wall-clock window
(shared ``clock_ns`` / monotonic_ns). Does not open capture devices.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

log = logging.getLogger(__name__)

# ~5 s at high event rate (edges only; not 1 kHz full state)
DEFAULT_CAPACITY = 4096
DEFAULT_MAX_AGE_S = 5.0

# Energy weights for simple activity score
_WEIGHT = {
    "press": 1.0,
    "release": 0.15,
    "trigger": 1.2,
    "stick": 0.4,
}


@dataclass
class InputEvent:
    """One input edge for ring storage / clip sidecar."""

    clock_ns: int
    kind: str  # "press" | "release" | "trigger" | "stick"
    name: str
    value: float = 1.0
    buttons_mask: int | None = None
    frame_seq: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Drop nulls for compact sidecars
        return {k: v for k, v in d.items() if v is not None}


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

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "count": len(self._events),
                "buttons": list(self._latest_buttons),
                "capacity": self._capacity,
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
