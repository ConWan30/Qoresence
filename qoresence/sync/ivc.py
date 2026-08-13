"""Input–Video Coupler (IVC) — co-occurrence of HID edges with frame stamps.

Observation plane only. Language: **coupling / co-occurrence** — not
verification of legitimacy or anti-cheat.

Formula (simple, documented):
  lag band: inputs with clock in [t_video - lag_hi, t_video - lag_lo]
  input_energy: InputRing.energy over that window (weighted presses)
  coupling: 1 - exp(-input_energy / energy_scale)  clipped to [0, 1]
            (smooth saturating map; more edges → higher coupling)
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

# Defaults: ~20–120 ms lookback (Pattern A VCam often needs up to ~200 ms hi)
DEFAULT_LAG_LO_MS = 20.0
DEFAULT_LAG_HI_MS = 120.0
DEFAULT_HZ = 15.0
DEFAULT_ENERGY_SCALE = 2.5


class InputVideoCoupler:
    """Background loop joining InputRing edges to FrameHub stamps."""

    def __init__(
        self,
        *,
        bus: Any = None,
        session_head_ns: int | None = None,
        lag_lo_ms: float = DEFAULT_LAG_LO_MS,
        lag_hi_ms: float = DEFAULT_LAG_HI_MS,
        hz: float = DEFAULT_HZ,
        energy_scale: float = DEFAULT_ENERGY_SCALE,
    ) -> None:
        self.bus = bus
        self.session_head_ns = session_head_ns
        self.lag_lo_ms = float(lag_lo_ms)
        self.lag_hi_ms = float(max(lag_hi_ms, lag_lo_ms + 1.0))
        self.hz = max(5.0, min(30.0, float(hz)))
        self.energy_scale = max(0.1, float(energy_scale))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last: dict[str, Any] = {
            "frame_seq": 0,
            "video_clock_ns": 0,
            "input_events": 0,
            "buttons": [],
            "input_energy": 0.0,
            "coupling": 0.0,
            "lag_band_ms": [self.lag_lo_ms, self.lag_hi_ms],
            "path": "fast",
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="input-video-coupler", daemon=True)
        self._thread.start()
        log.info(
            "IVC started (%.0f Hz, lag %.0f–%.0f ms) — co-occurrence only",
            self.hz,
            self.lag_lo_ms,
            self.lag_hi_ms,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        log.info("IVC stopped")

    def get_last_coupling(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last)

    def tick_once(self) -> dict[str, Any] | None:
        """One coupling sample (for tests / manual). Returns payload or None if no frame."""
        return self._sample()

    def _run(self) -> None:
        interval = 1.0 / self.hz
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                self._sample()
            except Exception as e:
                log.debug("IVC sample error: %s", e)
            elapsed = time.monotonic() - t0
            sleep = interval - elapsed
            if sleep > 0.001:
                self._stop.wait(timeout=sleep)

    def _sample(self) -> dict[str, Any] | None:
        t_sample0 = time.perf_counter()
        from qoresence.monitor.frame_hub import get_frame_hub
        from qoresence.sync.input_ring import get_input_ring

        stamp = get_frame_hub().get_latest_stamp()
        if not stamp.get("has_frame"):
            return None

        seq = int(stamp.get("seq") or 0)
        t_video = int(stamp.get("clock_ns") or 0)
        if t_video <= 0:
            return None

        lag_lo_ms, lag_hi_ms = self.lag_lo_ms, self.lag_hi_ms
        try:
            from qoresence.sync.event_bind import get_event_binder
            from qoresence.sync.lag_estimator import get_lag_estimator

            est = get_lag_estimator()
            last_lag = get_event_binder().last_lag_ms()
            if last_lag is not None:
                est.observe(last_lag)
            lag_lo_ms, lag_hi_ms = est.band(self.lag_lo_ms, self.lag_hi_ms)
        except Exception:
            pass
        lag_lo_ns = int(lag_lo_ms * 1e6)
        lag_hi_ns = int(lag_hi_ms * 1e6)
        # Inputs that occurred slightly *before* this frame (display lag band)
        t0 = t_video - lag_hi_ns
        t1 = t_video - lag_lo_ns

        ring = get_input_ring()
        events = ring.in_window(t0, t1)
        energy = 0.0
        for e in events:
            from qoresence.sync.input_ring import _WEIGHT

            energy += _WEIGHT.get(e.kind, 0.5) * min(1.5, abs(float(e.value)) + 0.25)

        coupling = 1.0 - math.exp(-energy / self.energy_scale)
        coupling = max(0.0, min(1.0, coupling))
        buttons = sorted({e.name for e in events if e.kind in ("press", "trigger")})
        if not buttons:
            buttons = ring.latest_buttons()[:8]

        payload = {
            "frame_seq": seq,
            "video_clock_ns": t_video,
            "input_events": len(events),
            "buttons": buttons,
            "input_energy": round(energy, 4),
            "coupling": round(coupling, 4),
            "lag_band_ms": [round(lag_lo_ms, 1), round(lag_hi_ms, 1)],
            # Two-speed ClutchBot: IVC is the realtime (fast) path signal
            "path": "fast",
        }
        precursors = [e.imu_precursor_ms for e in events if e.imu_precursor_ms is not None]
        if precursors:
            payload["imu_precursor_ms"] = round(sum(precursors) / len(precursors), 2)
            payload["imu_bodied"] = True
        else:
            payload["imu_bodied"] = False
        try:
            from qoresence.sync.event_bind import get_event_binder

            binds = get_event_binder().recent()
            if binds:
                payload["binds"] = len(binds)
                payload["last_bind_ms"] = binds[-1].lag_ms
                payload["last_bind_kind"] = binds[-1].visual_kind
        except Exception:
            pass
        try:
            from qoresence.sync.imu_ring import get_imu_ring
            from qoresence.sync.optical import StickMotionCoupler, frame_motion_energy

            if not hasattr(self, "_stick_opt"):
                self._stick_opt = StickMotionCoupler()
                self._prev_jpeg = None
            imu = get_imu_ring().last()
            stick_ev = [e for e in events if e.kind == "stick" and e.name == "right"]
            vx = float(stick_ev[-1].value) if stick_ev else 0.0
            gz = imu.gyro_z if imu else 0.0
            jpeg = None
            try:
                from qoresence.vision.clip_buffer import get_latest_jpeg

                jpeg = get_latest_jpeg()
            except Exception:
                jpeg = None
            motion = 0.0
            if jpeg is not None and self._prev_jpeg is not None:
                import cv2
                import numpy as np

                prev = cv2.imdecode(np.frombuffer(self._prev_jpeg, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                curr = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                if prev is not None and curr is not None:
                    motion = frame_motion_energy(prev, curr)
            if jpeg is not None:
                self._prev_jpeg = jpeg
            self._stick_opt.push(vx, gz, motion)
            opt = self._stick_opt.snapshot()
            payload["stick_gyro_r"] = opt["stick_gyro_r"]
            payload["stick_motion_r"] = opt["stick_motion_r"]
        except Exception:
            pass
        with self._lock:
            self._last = payload

        if self.bus is not None:
            try:
                from qoresence.core import SourceLobe

                self.bus.emit_raw(
                    source_lobe=SourceLobe.CONTROLLER,
                    event_type="coupling_score",
                    payload=payload,
                    clock_ns_override=t_video,
                    session_head_ns=self.session_head_ns,
                )
            except Exception as e:
                log.debug("IVC bus emit failed: %s", e)

        try:
            from qoresence.observability import record_latency

            record_latency(
                "ivc_tick",
                (time.perf_counter() - t_sample0) * 1000.0,
                frame_seq=seq,
            )
        except Exception:
            pass

        return payload


# Process singleton (optional; app may hold its own)
_ivc: InputVideoCoupler | None = None
_ivc_lock = threading.Lock()


def get_ivc() -> InputVideoCoupler | None:
    return _ivc


def start_ivc(
    *,
    bus: Any = None,
    session_head_ns: int | None = None,
    lag_lo_ms: float = DEFAULT_LAG_LO_MS,
    lag_hi_ms: float = DEFAULT_LAG_HI_MS,
) -> InputVideoCoupler:
    global _ivc
    with _ivc_lock:
        if _ivc is not None:
            try:
                _ivc.stop()
            except Exception:
                pass
        _ivc = InputVideoCoupler(
            bus=bus,
            session_head_ns=session_head_ns,
            lag_lo_ms=lag_lo_ms,
            lag_hi_ms=lag_hi_ms,
        )
        _ivc.start()
        return _ivc


def stop_ivc() -> None:
    global _ivc
    with _ivc_lock:
        if _ivc is not None:
            try:
                _ivc.stop()
            except Exception:
                pass
            _ivc = None


def get_last_coupling() -> dict[str, Any]:
    ivc = get_ivc()
    if ivc is None:
        return {
            "frame_seq": 0,
            "video_clock_ns": 0,
            "input_events": 0,
            "buttons": [],
            "input_energy": 0.0,
            "coupling": 0.0,
            "lag_band_ms": [DEFAULT_LAG_LO_MS, DEFAULT_LAG_HI_MS],
            "path": "fast",
        }
    out = ivc.get_last_coupling()
    out.setdefault("path", "fast")
    return out
