"""Adaptive HID→video lag (observation plane).

Two layers:

1. **Envelope band** — EventBinder lag samples may *widen* the IVC join
   window so VCam / slow HDMI still couple. We never shrink hi below the
   configured default (sliding a thin sliver 200 ms into the past is how
   live coupling died).

2. **Phase-locked loop** — IMU-bodied presses vs FrameHub ``clock_ns``
   estimate ``lag_center_ms``. The join *center* tracks this session's
   HDMI delay; width stays fat. Frozen video must not yank the PLL.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from typing import Any


class LagEstimator:
    def __init__(
        self,
        capacity: int = 48,
        lo_floor: float = 0.0,
        hi_ceil: float = 280.0,
        pll_alpha: float = 0.12,
    ) -> None:
        self._lock = threading.Lock()
        self._lags: deque[float] = deque(maxlen=capacity)
        self._phases: deque[float] = deque(maxlen=capacity)
        self.lo_floor = lo_floor
        self.hi_ceil = hi_ceil
        self.pll_alpha = max(0.02, min(0.5, float(pll_alpha)))
        self._center: float | None = None
        self._lock_count = 0

    def observe(self, lag_ms: float) -> None:
        if lag_ms < 4.0 or lag_ms > 280.0:
            return
        with self._lock:
            self._lags.append(float(lag_ms))

    def observe_phase(self, delta_ms: float, *, video_stale: bool = False) -> None:
        """IMU-bodied HID → FrameHub residual in milliseconds.

        ``delta_ms = (t_video - t_hid) / 1e6``. Skip when FrameHub is stale
        so a freeze cannot walk the PLL.
        """
        if video_stale:
            return
        if delta_ms < -40.0 or delta_ms > 280.0:
            return
        with self._lock:
            d = float(delta_ms)
            self._phases.append(d)
            if self._center is None:
                self._center = d
            else:
                a = self.pll_alpha
                self._center = a * d + (1.0 - a) * self._center
            self._lock_count = min(10_000, self._lock_count + 1)

    def band(self, default_lo: float, default_hi: float) -> tuple[float, float]:
        with self._lock:
            if len(self._lags) < 4:
                return self._band_from_pll_locked(default_lo, default_hi)
            vals = sorted(self._lags)
            center = self._center
            jitter = self._jitter_locked()
        mid = vals[len(vals) // 2]
        p20 = vals[max(0, len(vals) // 5)]
        p80 = vals[min(len(vals) - 1, (4 * len(vals)) // 5)]
        observed_lo = min(mid, p20) - 12.0
        observed_hi = max(mid, p80) + 24.0
        lo = min(float(default_lo), max(self.lo_floor, observed_lo))
        lo = max(0.0, lo)
        hi = max(float(default_hi), observed_hi)
        hi = min(self.hi_ceil, hi)
        if center is not None and jitter is not None:
            half = max(float(default_hi) * 0.5, 1.5 * jitter + 24.0)
            pll_lo = max(0.0, center - half)
            pll_hi = min(self.hi_ceil, center + half)
            # Envelope: never thinner than configured default width.
            lo = min(lo, pll_lo)
            hi = max(hi, pll_hi, lo + (float(default_hi) - float(default_lo)))
        if hi <= lo + 8.0:
            hi = lo + 40.0
        return lo, hi

    def _band_from_pll_locked(self, default_lo: float, default_hi: float) -> tuple[float, float]:
        if self._center is None or len(self._phases) < 4:
            return default_lo, default_hi
        jitter = self._jitter_locked() or 24.0
        half = max(float(default_hi) * 0.5, 1.5 * jitter + 24.0)
        lo = max(0.0, min(float(default_lo), self._center - half))
        hi = max(float(default_hi), min(self.hi_ceil, self._center + half))
        if hi <= lo + 8.0:
            hi = lo + 40.0
        return lo, hi

    def _jitter_locked(self) -> float | None:
        if len(self._phases) < 4:
            return None
        mean = self._center if self._center is not None else 0.0
        acc = 0.0
        for p in self._phases:
            d = p - mean
            acc += d * d
        return math.sqrt(acc / len(self._phases))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            jitter = self._jitter_locked()
            n = len(self._phases)
            center = self._center
            lock = bool(n >= 8 and jitter is not None and jitter <= 28.0)
        return {
            "lag_center_ms": None if center is None else round(float(center), 2),
            "lag_jitter_ms": None if jitter is None else round(float(jitter), 2),
            "pll_lock": lock,
            "pll_n": n,
        }

    def n(self) -> int:
        with self._lock:
            return len(self._lags)

    def reset(self) -> None:
        with self._lock:
            self._lags.clear()
            self._phases.clear()
            self._center = None
            self._lock_count = 0


_est = LagEstimator()


def get_lag_estimator() -> LagEstimator:
    return _est
