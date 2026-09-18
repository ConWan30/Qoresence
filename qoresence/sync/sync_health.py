"""Sync health — deterministic lag-state machine for the capture plane.

States: ``smooth`` → ``tight`` → ``shedding``. Inputs are plain telemetry
(frame cadence, measured fps, video age). Outputs are knobs other lobes
read — today the controller HID coalesce rate; the SyncCoroner may
*recommend* a level via :meth:`set_level` but code owns transitions.

Observation-plane class: never emits bus events, never takes a lobe lock.
All methods are cheap enough to call per frame / per HID report.
"""

from __future__ import annotations

import threading
import time
from typing import Any

SMOOTH = "smooth"
TIGHT = "tight"
SHEDDING = "shedding"
LEVELS = (SMOOTH, TIGHT, SHEDDING)

# Knob tables — one source of truth for level → mitigation strength.
_COALESCE_HZ = {SMOOTH: 10.0, TIGHT: 5.0, SHEDDING: 2.0}
_VLM_INTERVAL_MULT = {SMOOTH: 1.0, TIGHT: 1.5, SHEDDING: 3.0}

# Hysteresis: a condition must hold this long before it drives a transition.
_ENTER_TIGHT_S = 1.0
_ENTER_SHED_S = 2.0
_RECOVER_TIGHT_S = 5.0
_RECOVER_SMOOTH_S = 3.0
_WARMUP_S = 2.0  # ignore degradation while capture is still spinning up
_OVERRIDE_COOLDOWN_S = 10.0  # external set_level holds vs auto-eval


class SyncHealth:
    """Lag-state machine fed by streamer/controller telemetry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._level = SMOOTH
        self._last_frame_mono: float | None = None
        self._frame_delta_ema: float | None = None
        self._fps_meas = 0.0
        self._fps_target = 0.0
        self._video_age_s = 0.0
        self._rates_since_mono: float | None = None
        self._cond_since: dict[str, float] = {}
        self._override: tuple[str, float, str] | None = None  # (level, until_mono, reason)
        self._transitions: list[dict[str, Any]] = []
        self._frames_seen = 0

    # ── inputs (cheap; called from streamer/controller threads) ──────────

    def note_frame(self) -> None:
        """Called once per captured frame — tracks inter-frame cadence EMA."""
        now = time.monotonic()
        with self._lock:
            if self._last_frame_mono is not None:
                d = now - self._last_frame_mono
                self._frame_delta_ema = (
                    d if self._frame_delta_ema is None else self._frame_delta_ema * 0.9 + d * 0.1
                )
            self._last_frame_mono = now
            self._frames_seen += 1

    def note_rates(
        self,
        *,
        fps_meas: float,
        fps_target: float,
        video_age_s: float | None = None,
    ) -> str:
        """Periodic rates (streamer stats tick). Triggers re-evaluation."""
        with self._lock:
            self._fps_meas = float(fps_meas or 0.0)
            self._fps_target = float(fps_target or 0.0)
            if video_age_s is not None:
                self._video_age_s = float(video_age_s)
            if self._rates_since_mono is None:
                self._rates_since_mono = time.monotonic()
        return self.evaluate()

    # ── evaluation ───────────────────────────────────────────────────────

    def _fps_ratio_locked(self) -> float | None:
        if self._fps_target <= 0:
            return None
        return self._fps_meas / self._fps_target

    def _warmed_up_locked(self, now: float) -> bool:
        return self._rates_since_mono is not None and (now - self._rates_since_mono) >= _WARMUP_S

    def _degraded_locked(self, now: float) -> bool:
        if not self._warmed_up_locked(now):
            return False
        ratio = self._fps_ratio_locked()
        if ratio is not None and ratio < 0.7:
            return True
        return self._video_age_s > 0.5

    def _critical_locked(self, now: float) -> bool:
        if not self._warmed_up_locked(now):
            return False
        ratio = self._fps_ratio_locked()
        if ratio is not None and ratio < 0.4:
            return True
        return self._video_age_s > 1.0

    def _healthy_locked(self) -> bool:
        ratio = self._fps_ratio_locked()
        if ratio is not None and ratio >= 0.85 and self._video_age_s < 0.5:
            return True
        return False

    def _held(self, name: str, cond: bool, now: float, need_s: float) -> bool:
        """True when `cond` has held continuously for `need_s`."""
        if not cond:
            self._cond_since.pop(name, None)
            return False
        start = self._cond_since.setdefault(name, now)
        return (now - start) >= need_s

    def evaluate(self, now: float | None = None) -> str:
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._override is not None:
                o_level, until, _reason = self._override
                if now < until:
                    self._level = o_level
                    return self._level
                self._override = None

            degraded = self._degraded_locked(now)
            critical = self._critical_locked(now)
            healthy = self._healthy_locked()

            level = self._level
            if level == SMOOTH:
                if self._held("degraded", degraded, now, _ENTER_TIGHT_S):
                    level = TIGHT
            elif level == TIGHT:
                if self._held("critical", critical, now, _ENTER_SHED_S):
                    level = SHEDDING
                elif self._held("healthy", healthy, now, _RECOVER_SMOOTH_S):
                    level = SMOOTH
            elif level == SHEDDING:
                if self._held("healthy", healthy, now, _RECOVER_TIGHT_S):
                    level = TIGHT
            # Critical while smooth jumps straight past tight only via tight —
            # one step per evaluation keeps transitions legible.
            if level != self._level:
                self._transitions.append(
                    {
                        "from": self._level,
                        "to": level,
                        "mono": now,
                        "fps_meas": round(self._fps_meas, 2),
                        "fps_target": round(self._fps_target, 2),
                        "video_age_s": round(self._video_age_s, 3),
                    }
                )
                self._transitions = self._transitions[-32:]
                self._level = level
            return self._level

    # ── knobs other lobes read ───────────────────────────────────────────

    def level(self) -> str:
        with self._lock:
            return self._level

    def coalesce_hz(self) -> float:
        """Bus-emit ceiling for high-rate HID telemetry."""
        return _COALESCE_HZ[self.level()]

    def vlm_interval_mult(self) -> float:
        """Interval multiplier optional consumers (VLM cadence) may apply."""
        return _VLM_INTERVAL_MULT[self.level()]

    def set_level(self, level: str, *, reason: str = "", source: str = "external") -> str:
        """Externally requested level (SyncCoroner). Held for a cooldown so a
        single noisy judgment can't fight the hysteresis loop."""
        if level not in LEVELS:
            return self.level()
        with self._lock:
            self._override = (level, time.monotonic() + _OVERRIDE_COOLDOWN_S, f"{source}:{reason}")
            self._transitions.append(
                {
                    "from": self._level,
                    "to": level,
                    "mono": time.monotonic(),
                    "source": source,
                    "reason": reason,
                }
            )
            self._transitions = self._transitions[-32:]
            self._level = level
            return self._level

    def stats(self) -> dict[str, Any]:
        # Compute knobs inline — level()/coalesce_hz() re-acquire this lock,
        # which is non-reentrant (calling them here would self-deadlock).
        with self._lock:
            level = self._level
            return {
                "level": level,
                "coalesce_hz": _COALESCE_HZ[level],
                "vlm_interval_mult": _VLM_INTERVAL_MULT[level],
                "fps_meas": round(self._fps_meas, 2),
                "fps_target": round(self._fps_target, 2),
                "fps_ratio": (
                    round(self._fps_meas / self._fps_target, 3) if self._fps_target > 0 else None
                ),
                "video_age_s": round(self._video_age_s, 3),
                "frame_delta_ema_ms": (
                    round(self._frame_delta_ema * 1000, 2)
                    if self._frame_delta_ema is not None
                    else None
                ),
                "frames_seen": self._frames_seen,
                "override": self._override[2] if self._override else None,
                "transitions": list(self._transitions[-8:]),
            }


_singleton: SyncHealth | None = None
_singleton_lock = threading.Lock()


def get_sync_health() -> SyncHealth:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = SyncHealth()
        return _singleton


def reset_sync_health() -> SyncHealth:
    """Tests: fresh machine."""
    global _singleton
    with _singleton_lock:
        _singleton = SyncHealth()
        return _singleton
