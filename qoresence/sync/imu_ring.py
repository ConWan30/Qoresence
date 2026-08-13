"""IMU sample ring + L2B press precursor (observation plane).

Forked from QorTroller ``l2b_imu_press_correlation.py`` physics, not its
cheat codes. A real press has a gyro micro-impulse 5–80 ms *before* the
digital edge. Software-only edges have none.

Units: gyro is DualSense int16 / 1000.0 (live hardware path). Spike
threshold 0.03 matches QorTroller's live-verified scale.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

PRECURSOR_MIN_MS = 5.0
PRECURSOR_MAX_MS = 80.0
IMU_SPIKE_THRESH = 0.03  # scaled gyro mag above rolling baseline
BASELINE_N = 24


@dataclass
class ImuSample:
    clock_ns: int
    gyro_x: float
    gyro_y: float
    gyro_z: float
    accel_x: float
    accel_y: float
    accel_z: float
    frame_seq: int | None = None

    @property
    def gyro_mag(self) -> float:
        return math.sqrt(self.gyro_x**2 + self.gyro_y**2 + self.gyro_z**2)


class ImuRing:
    """~1 s of 1 kHz IMU at most (bounded)."""

    def __init__(self, capacity: int = 1200) -> None:
        self._lock = threading.Lock()
        self._samples: deque[ImuSample] = deque(maxlen=max(64, capacity))

    def push(self, sample: ImuSample) -> None:
        with self._lock:
            self._samples.append(sample)

    def push_raw(
        self,
        clock_ns: int,
        gyro: tuple[int, int, int],
        accel: tuple[int, int, int],
        frame_seq: int | None = None,
    ) -> None:
        self.push(
            ImuSample(
                clock_ns=clock_ns,
                gyro_x=gyro[0] / 1000.0,
                gyro_y=gyro[1] / 1000.0,
                gyro_z=gyro[2] / 1000.0,
                accel_x=accel[0] / 1000.0,
                accel_y=accel[1] / 1000.0,
                accel_z=accel[2] / 1000.0,
                frame_seq=frame_seq,
            )
        )

    def precursor_ms(
        self,
        press_ns: int,
        *,
        min_ms: float = PRECURSOR_MIN_MS,
        max_ms: float = PRECURSOR_MAX_MS,
        thresh: float = IMU_SPIKE_THRESH,
    ) -> float | None:
        """Ms before ``press_ns`` of the strongest gyro spike in the precursor window.

        None = no body-motion precursor (digital edge only).
        """
        lo = press_ns - int(max_ms * 1e6)
        hi = press_ns - int(min_ms * 1e6)
        with self._lock:
            window = [s for s in self._samples if lo <= s.clock_ns <= hi]
            prior = [s for s in self._samples if s.clock_ns < lo][-BASELINE_N:]
        if not window:
            return None
        baseline = (
            sum(s.gyro_mag for s in prior) / len(prior) if prior else sum(s.gyro_mag for s in window) / len(window)
        )
        best: ImuSample | None = None
        best_excess = 0.0
        for s in window:
            excess = s.gyro_mag - baseline
            if excess >= thresh and excess > best_excess:
                best = s
                best_excess = excess
        if best is None:
            return None
        return (press_ns - best.clock_ns) / 1e6

    def last(self) -> ImuSample | None:
        with self._lock:
            return self._samples[-1] if self._samples else None

    def snapshot(self, since_ns: int | None = None) -> list[ImuSample]:
        with self._lock:
            if since_ns is None:
                return list(self._samples)
            return [s for s in self._samples if s.clock_ns >= since_ns]


_ring = ImuRing()
_ring_lock = threading.Lock()


def get_imu_ring() -> ImuRing:
    return _ring


def push_imu(**kw: Any) -> None:
    try:
        get_imu_ring().push_raw(
            clock_ns=int(kw.get("clock_ns") or time.monotonic_ns()),
            gyro=tuple(kw.get("gyro") or (0, 0, 0)),  # type: ignore[arg-type]
            accel=tuple(kw.get("accel") or (0, 0, 0)),  # type: ignore[arg-type]
            frame_seq=kw.get("frame_seq"),
        )
    except Exception:
        pass
