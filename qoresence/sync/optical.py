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
