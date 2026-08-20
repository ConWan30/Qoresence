"""Cheap FrameHub motion energy + stick/gyro coupling (COD profile).

Forked in spirit from QorTroller ``coupling.py`` / ``l2c`` — Pearson of
right-stick velocity vs gyro_z / frame motion. Observation only.
"""

from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np


def frame_motion_energy(prev: np.ndarray | None, curr: np.ndarray | None) -> float:
    if prev is None or curr is None:
        return 0.0
    if prev.shape != curr.shape:
        return 0.0
    a = prev.astype(np.float32)
    b = curr.astype(np.float32)
    if a.ndim == 3:
        a = a.mean(axis=2)
        b = b.mean(axis=2)
    return float(np.mean(np.abs(a - b)))


def bind_offset_ms(
    luma_ring: list[dict],
    hid_ns: int,
    gyro_sign: float = 0.0,
) -> tuple[float | None, float]:
    """Sub-frame HID→picture residual from FrameHub luma stamps.

    Search ±2 frames around the HID edge for the first luma-energy onset.
    Returns ``(offset_ms, confidence)``. Offset is ``t_luma − t_hid`` in ms,
    clipped to roughly one 60 Hz frame. Observation only.
    """
    if not luma_ring or hid_ns <= 0:
        return None, 0.0
    rows = [r for r in luma_ring if int(r.get("clock_ns") or 0) > 0]
    if len(rows) < 2:
        return None, 0.0
    best: tuple[float, float] | None = None
    prev_e = float(rows[0].get("energy") or 0.0)
    for r in rows[1:]:
        e = float(r.get("energy") or 0.0)
        t = int(r.get("clock_ns") or 0)
        delta_ms = (t - hid_ns) / 1e6
        if delta_ms < -40.0 or delta_ms > 48.0:
            prev_e = e
            continue
        onset = e - prev_e
        prev_e = e
        if onset < 0.8:
            continue
        conf = min(1.0, onset / 12.0)
        if gyro_sign != 0.0:
            # Prefer onsets in the same temporal half as the IMU jolt direction
            # without claiming we measured look-axis in the picture.
            conf *= 1.05
            conf = min(1.0, conf)
        if best is None or conf > best[1]:
            best = (max(-16.0, min(16.0, delta_ms)), conf)
    if best is None:
        return None, 0.0
    return round(best[0], 2), round(best[1], 3)


def pearson(x: list[float], y: list[float]) -> float:
    n = min(len(x), len(y))
    if n < 8:
        return 0.0
    xa = np.asarray(x[-n:], dtype=np.float64)
    ya = np.asarray(y[-n:], dtype=np.float64)
    xa = xa - xa.mean()
    ya = ya - ya.mean()
    den = float(np.sqrt((xa * xa).sum() * (ya * ya).sum()))
    if den < 1e-9:
        return 0.0
    return float((xa * ya).sum() / den)


class StickMotionCoupler:
    """Rolling right-stick vx vs gyro_z and vs frame motion."""

    def __init__(self, n: int = 48) -> None:
        self.vx: deque[float] = deque(maxlen=n)
        self.gyro_z: deque[float] = deque(maxlen=n)
        self.motion: deque[float] = deque(maxlen=n)

    def push(self, vx: float, gyro_z: float, motion: float) -> None:
        self.vx.append(vx)
        self.gyro_z.append(gyro_z)
        self.motion.append(motion)

    def snapshot(self) -> dict[str, Any]:
        r_imu = pearson(list(self.vx), list(self.gyro_z))
        r_opt = pearson(list(self.vx), list(self.motion))
        return {
            "stick_gyro_r": round(r_imu, 4),
            "stick_motion_r": round(r_opt, 4),
            "coupled": bool(abs(r_imu) >= 0.15 or abs(r_opt) >= 0.12),
            "n": len(self.vx),
        }
