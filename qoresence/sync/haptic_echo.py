"""IMU actuator-echo detector — DualSense pad as its own contact mic.

Novelty: existing ``ImuRing.precursor_ms`` looks for a *brief gyro jolt
5–80 ms before a digital edge* (L2B press physics). This detector looks
for *sustained high-pass accel energy* while analog slew is quiet — the
signature of the pad's voice-coil / rumble actuators shaking the IMU.

Interoperable with IVC: pulses are stamped with the same ``clock_ns`` as
HID/IMU and later joined to the IVC lag band. They do not name buttons
and do not license score digits.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from qoresence.sync.haptic_schema import intensity_bucket

ONSET_SCORE = 48.0
OFF_SCORE = 22.0
DWELL_ON = 14
DWELL_OFF = 22
ANALOG_K = 55.0
MIN_DURATION_MS = 20.0
JERK_WINDOW = 12
SUSTAINED_MS = 120.0


@dataclass(frozen=True)
class HapticPulse:
    t_start_ns: int
    t_end_ns: int
    intensity: str
    intensity_01: float
    channel: str
    signature: str | None
    actuators: tuple[str, ...]
    peak_score: float
    transport: str
    hid_present: bool

    @property
    def duration_ms(self) -> float:
        return max(0.0, (self.t_end_ns - self.t_start_ns) / 1e6)


def _mag(accel: tuple[int, int, int]) -> float:
    x, y, z = (float(accel[0]), float(accel[1]), float(accel[2]))
    return math.sqrt(x * x + y * y + z * z)


def _signature(duration_ms: float) -> str:
    if duration_ms >= SUSTAINED_MS:
        return "sustained"
    return "impact_candidate"


class EchoDetector:
    """Streaming onset/offset for IMU actuator echo. Pure-ish; no I/O."""

    def __init__(self) -> None:
        self._mags: deque[float] = deque(maxlen=JERK_WINDOW + 1)
        self._jerks: deque[float] = deque(maxlen=JERK_WINDOW)
        self._above = 0
        self._below = 0
        self._active = False
        self._t_start = 0
        self._t_last = 0
        self._peak = 0.0
        self._transport = "unknown"
        self._hid_present = False

    def feed(
        self,
        *,
        clock_ns: int,
        accel: tuple[int, int, int],
        gyro: tuple[int, int, int] = (0, 0, 0),  # noqa: ARG002 — reserved; not used for onset
        analog_slew: float = 0.0,
        transport: str = "unknown",
        hid_present: bool = False,
        channel: str = "imu_echo",
    ) -> HapticPulse | None:
        mag = _mag(accel)
        jerk = 0.0
        if self._mags:
            jerk = abs(mag - self._mags[-1])
            self._jerks.append(jerk)
        self._mags.append(mag)
        if not self._jerks:
            return None
        mean_jerk = sum(self._jerks) / len(self._jerks)
        score = mean_jerk - ANALOG_K * max(0.0, float(analog_slew))
        ts = int(clock_ns)
        if score >= ONSET_SCORE:
            self._above += 1
            self._below = 0
        else:
            self._below += 1
            self._above = 0

        if not self._active:
            if self._above >= DWELL_ON:
                self._active = True
                dwell_ns = int(DWELL_ON * 1e6)
                self._t_start = ts - dwell_ns
                self._t_last = ts
                self._peak = score
                self._transport = str(transport or "unknown")
                self._hid_present = bool(hid_present)
            return None

        self._t_last = ts
        if score > self._peak:
            self._peak = score
        if hid_present:
            self._hid_present = True
        if transport:
            self._transport = str(transport)
        if self._below >= DWELL_OFF:
            return self._close(ts, channel=channel)
        return None

    def close_open(self, clock_ns: int, *, channel: str = "imu_echo") -> HapticPulse | None:
        if not self._active:
            return None
        return self._close(int(clock_ns), channel=channel)

    def _close(self, t_end: int, *, channel: str) -> HapticPulse | None:
        t0 = int(self._t_start)
        self._active = False
        self._above = 0
        self._below = 0
        dur_ms = (t_end - t0) / 1e6
        if dur_ms < MIN_DURATION_MS:
            return None
        peak = float(self._peak)
        intensity_01 = max(0.0, min(1.0, (peak - 30.0) / 400.0))
        bucket = intensity_bucket(intensity_01) or "low"
        hid = self._hid_present
        transport = self._transport or "unknown"
        self._peak = 0.0
        self._hid_present = False
        return HapticPulse(
            t_start_ns=t0,
            t_end_ns=int(t_end),
            intensity=bucket,
            intensity_01=intensity_01,
            channel=channel,
            signature=_signature(dur_ms),
            actuators=("mixed",),
            peak_score=peak,
            transport=transport,
            hid_present=hid,
        )


class RumbleTracker:
    """Onset/offset from DualSense output-report rumble bytes."""

    def __init__(self) -> None:
        self._active = False
        self._t_start = 0
        self._peak_l = 0
        self._peak_r = 0
        self._transport = "unknown"
        self._hid_present = False

    def feed(
        self,
        *,
        clock_ns: int,
        rumble_left: int,
        rumble_right: int,
        transport: str = "unknown",
        hid_present: bool = False,
    ) -> HapticPulse | None:
        left = max(0, min(255, int(rumble_left)))
        right = max(0, min(255, int(rumble_right)))
        on = left > 0 or right > 0
        ts = int(clock_ns)
        if on and not self._active:
            self._active = True
            self._t_start = ts
            self._peak_l = left
            self._peak_r = right
            self._transport = str(transport or "unknown")
            self._hid_present = bool(hid_present)
            return None
        if on and self._active:
            self._peak_l = max(self._peak_l, left)
            self._peak_r = max(self._peak_r, right)
            if hid_present:
                self._hid_present = True
            if transport:
                self._transport = str(transport)
            return None
        if (not on) and self._active:
            return self._close(ts)
        return None

    def close_open(self, clock_ns: int) -> HapticPulse | None:
        if not self._active:
            return None
        return self._close(int(clock_ns))

    def _close(self, t_end: int) -> HapticPulse | None:
        t0 = int(self._t_start)
        self._active = False
        dur_ms = (t_end - t0) / 1e6
        if dur_ms < 1.0:
            return None
        peak = max(self._peak_l, self._peak_r) / 255.0
        acts: list[str] = []
        if self._peak_l > 0:
            acts.append("left")
        if self._peak_r > 0:
            acts.append("right")
        hid = self._hid_present
        transport = self._transport or "unknown"
        pl, pr = self._peak_l, self._peak_r
        self._peak_l = 0
        self._peak_r = 0
        self._hid_present = False
        return HapticPulse(
            t_start_ns=t0,
            t_end_ns=int(t_end),
            intensity=intensity_bucket(peak) or "low",
            intensity_01=peak,
            channel="hid_output",
            signature=_signature(dur_ms),
            actuators=tuple(acts) or ("mixed",),
            peak_score=float(max(pl, pr)),
            transport=transport,
            hid_present=hid,
        )
