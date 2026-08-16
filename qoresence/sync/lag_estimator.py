"""Adaptive HID→video lag from temporal binds (observation plane).

QorTroller measures this as cross-channel latency. Qoresence IVC uses a
configured join window; when EventBinder has pairs we may *widen* hi to
cover slower capture paths (VCam). We never raise lo or shrink hi —
sliding a 30 ms sliver 200 ms into the past is how live coupling died.
"""

from __future__ import annotations

import threading
from collections import deque


class LagEstimator:
    def __init__(self, capacity: int = 48, lo_floor: float = 0.0, hi_ceil: float = 280.0) -> None:
        self._lock = threading.Lock()
        self._lags: deque[float] = deque(maxlen=capacity)
        self.lo_floor = lo_floor
        self.hi_ceil = hi_ceil

    def observe(self, lag_ms: float) -> None:
        if lag_ms < 4.0 or lag_ms > 280.0:
            return
        with self._lock:
            self._lags.append(float(lag_ms))

    def band(self, default_lo: float, default_hi: float) -> tuple[float, float]:
        with self._lock:
            if len(self._lags) < 4:
                return default_lo, default_hi
            vals = sorted(self._lags)
        mid = vals[len(vals) // 2]
        p20 = vals[max(0, len(vals) // 5)]
        p80 = vals[min(len(vals) - 1, (4 * len(vals)) // 5)]
        observed_lo = min(mid, p20) - 12.0
        observed_hi = max(mid, p80) + 24.0
        # Envelope: configured window is the floor. Observed lag only widens.
        lo = min(float(default_lo), max(self.lo_floor, observed_lo))
        lo = max(0.0, lo)
        hi = max(float(default_hi), observed_hi)
        hi = min(self.hi_ceil, hi)
        if hi <= lo + 8.0:
            hi = lo + 40.0
        return lo, hi

    def n(self) -> int:
        with self._lock:
            return len(self._lags)


_est = LagEstimator()


def get_lag_estimator() -> LagEstimator:
    return _est
