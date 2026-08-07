"""Process-local frame hub for Retina Monitor + Input–Video Coupler.

StreamerRuntime publishes BGR frames already owned by Qoresence.
Native monitor and IVC pull latest via get_latest / get_latest_stamp —
never open DShow.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


class FrameHub:
    """Thread-safe latest-frame slot with monotonic sequence + clock_ns."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._seq: int = 0
        self._ts: float = 0.0  # monotonic seconds (age)
        self._clock_ns: int = 0  # monotonic_ns at publish (join to inputs)
        self._publishes: int = 0

    def publish(
        self,
        frame_bgr: np.ndarray | None,
        clock_ns: int | None = None,
        seq: int | None = None,
    ) -> None:
        """Store a copy of the latest BGR frame. Never raises into capture loop.

        ``seq`` is ignored when None (auto-increment). Pass only for tests.
        ``clock_ns`` defaults to ``time.monotonic_ns()`` (same clock as HID).
        """
        if frame_bgr is None:
            return
        try:
            if not hasattr(frame_bgr, "shape") or len(frame_bgr.shape) < 2:
                return
            # Copy so streamer can overwrite its capture buffer safely
            snap = np.ascontiguousarray(frame_bgr.copy())
            ts_ns = int(clock_ns) if clock_ns is not None else time.monotonic_ns()
            with self._lock:
                self._frame = snap
                if seq is not None:
                    self._seq = int(seq)
                else:
                    self._seq += 1
                self._ts = time.monotonic()
                self._clock_ns = ts_ns
                self._publishes += 1
        except Exception as e:
            log.debug("FrameHub.publish failed: %s", e)

    def get_latest(self) -> np.ndarray | None:
        """Return a copy of the latest frame, or None if empty."""
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def get_latest_meta(self) -> tuple[np.ndarray | None, int, float]:
        """Return (frame_copy|None, seq, age_s) — monitor-compatible 3-tuple."""
        with self._lock:
            if self._frame is None:
                return None, 0, 0.0
            age = time.monotonic() - self._ts if self._ts else 0.0
            return self._frame.copy(), self._seq, age

    def get_latest_stamp(self) -> dict[str, Any]:
        """Cheap meta without frame copy: seq, clock_ns, has_frame, age_s."""
        with self._lock:
            if self._frame is None:
                return {
                    "has_frame": False,
                    "seq": 0,
                    "clock_ns": 0,
                    "age_s": None,
                }
            age = time.monotonic() - self._ts if self._ts else 0.0
            return {
                "has_frame": True,
                "seq": self._seq,
                "clock_ns": self._clock_ns,
                "age_s": round(float(age), 3),
            }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            age = (time.monotonic() - self._ts) if self._frame is not None and self._ts else None
            h = int(self._frame.shape[0]) if self._frame is not None else 0
            w = int(self._frame.shape[1]) if self._frame is not None else 0
            return {
                "has_frame": self._frame is not None,
                "seq": self._seq,
                "clock_ns": self._clock_ns,
                "publishes": self._publishes,
                "width": w,
                "height": h,
                "age_s": None if age is None else round(float(age), 3),
            }

    def clear(self) -> None:
        with self._lock:
            self._frame = None
            self._seq = 0
            self._ts = 0.0
            self._clock_ns = 0


# Process-wide hub (streamer + monitor + IVC share this process)
_hub = FrameHub()
_hub_lock = threading.Lock()


def get_frame_hub() -> FrameHub:
    return _hub


def publish(
    frame_bgr: np.ndarray | None,
    clock_ns: int | None = None,
    seq: int | None = None,
) -> None:
    """Module helper — best-effort publish for streamer loop."""
    try:
        get_frame_hub().publish(frame_bgr, clock_ns=clock_ns, seq=seq)
    except Exception:
        pass


def get_latest() -> np.ndarray | None:
    return get_frame_hub().get_latest()


def get_latest_stamp() -> dict[str, Any]:
    return get_frame_hub().get_latest_stamp()
