"""Input–Video Coupler (IVC) — co-occurrence of HID with frame stamps.

Observation plane only. Language: **coupling / co-occurrence** — not
verification of legitimacy or anti-cheat.

Formula (simple, documented):
  join window: [t_video - lag_hi, t_video - lag_lo + lead]
               default lag_lo=0, lead≈1 frame so near-simultaneous HID
               still joins (Pattern B card stamps are nearly contemporaneous)
  edge_energy: weighted InputRing edges inside that window
  hold_energy: live analog sustain (R2/L2/sticks) if HID hold is fresh
  input_energy: edge_energy + hold_energy
  coupling: 1 - exp(-input_energy / energy_scale)  clipped to [0, 1]
            then decayed if the FrameHub stamp is stale
  coupling_ema: exponential moving average of coupling (display / A2A)
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

# Defaults: contemporaneous join + ~120 ms lookback.
# Pattern A VCam often needs up to ~200 ms hi (QORESENCE_IVC_LAG_HI_MS).
DEFAULT_LAG_LO_MS = 0.0
DEFAULT_LAG_HI_MS = 120.0
DEFAULT_LEAD_MS = 24.0
DEFAULT_HZ = 30.0
DEFAULT_ENERGY_SCALE = 2.5
DEFAULT_EMA_ALPHA = 0.40
DEFAULT_HOLD_FRESH_MS = 80.0
# FrameHub age above this starts decaying coupling (stalled video ≠ live sync)
_STALE_AGE_S = 0.20
_STALE_TAU_S = 0.30


class InputVideoCoupler:
    """Background loop joining InputRing edges to FrameHub stamps."""

    def __init__(
        self,
        *,
        bus: Any = None,
        session_head_ns: int | None = None,
        lag_lo_ms: float = DEFAULT_LAG_LO_MS,
        lag_hi_ms: float = DEFAULT_LAG_HI_MS,
        lead_ms: float = DEFAULT_LEAD_MS,
        hz: float = DEFAULT_HZ,
        energy_scale: float = DEFAULT_ENERGY_SCALE,
        ema_alpha: float = DEFAULT_EMA_ALPHA,
        hold_fresh_ms: float = DEFAULT_HOLD_FRESH_MS,
    ) -> None:
        self.bus = bus
        self.session_head_ns = session_head_ns
        self.lag_lo_ms = float(max(0.0, lag_lo_ms))
        self.lag_hi_ms = float(max(lag_hi_ms, self.lag_lo_ms + 1.0))
        self.lead_ms = float(max(0.0, min(80.0, lead_ms)))
        self.hz = max(5.0, min(60.0, float(hz)))
        self.energy_scale = max(0.1, float(energy_scale))
        self.ema_alpha = max(0.05, min(1.0, float(ema_alpha)))
        self.hold_fresh_ms = max(20.0, float(hold_fresh_ms))
        self._ema = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last: dict[str, Any] = {
            "frame_seq": 0,
            "video_clock_ns": 0,
            "input_events": 0,
            "buttons": [],
            "input_energy": 0.0,
            "edge_energy": 0.0,
            "hold_energy": 0.0,
            "coupling": 0.0,
            "coupling_ema": 0.0,
            "lag_band_ms": [self.lag_lo_ms, self.lag_hi_ms],
            "lead_ms": self.lead_ms,
            "path": "fast",
            "imu_bodied": False,
            "binds": 0,
            "phrase": "IDLE",
            "phrase_conf": 0.0,
            "coupling_ticket_id": "",
        }
        self._prev_r2 = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="input-video-coupler", daemon=True)
        self._thread.start()
        log.info(
            "IVC started (%.0f Hz, lag %.0f–%.0f ms, lead %.0f ms) — co-occurrence only",
            self.hz,
            self.lag_lo_ms,
            self.lag_hi_ms,
            self.lead_ms,
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
        lead_ns = int(self.lead_ms * 1e6)
        # Edges in [t_video - lag_hi, t_video - lag_lo + lead].
        # lead covers one-frame HID/video clock skew on Pattern B cards.
        t0 = t_video - lag_hi_ns
        t1 = t_video - lag_lo_ns + lead_ns

        ring = get_input_ring()
        events = ring.in_window(t0, t1)
        from qoresence.sync.input_ring import _WEIGHT

        edge_energy = 0.0
        for e in events:
            edge_energy += _WEIGHT.get(e.kind, 0.5) * min(1.5, abs(float(e.value)) + 0.25)

        now_ns = time.monotonic_ns()
        hold_energy = 0.0
        try:
            hold_energy = float(
                ring.hold_energy(now_ns=now_ns, max_age_ms=self.hold_fresh_ms)
            )
        except Exception:
            hold_energy = 0.0

        age_s = stamp.get("age_s")
        try:
            age_s = float(age_s) if age_s is not None else 0.0
        except (TypeError, ValueError):
            age_s = 0.0
        # Stalled video must not keep scoring live analog as in-sync
        if age_s > _STALE_AGE_S:
            decay = math.exp(-(age_s - _STALE_AGE_S) / _STALE_TAU_S)
            hold_energy *= decay

        energy = edge_energy + hold_energy
        coupling = 1.0 - math.exp(-energy / self.energy_scale)
        coupling = max(0.0, min(1.0, coupling))
        if age_s > _STALE_AGE_S:
            coupling *= math.exp(-(age_s - _STALE_AGE_S) / _STALE_TAU_S)
            coupling = max(0.0, min(1.0, coupling))

        self._ema = self.ema_alpha * coupling + (1.0 - self.ema_alpha) * self._ema
        self._ema = max(0.0, min(1.0, self._ema))

        buttons = sorted({e.name for e in events if e.kind in ("press", "trigger")})
        if not buttons:
            buttons = ring.latest_buttons()[:8]
        hold_snap = None
        try:
            hold_snap = ring.hold()
            if not buttons:
                buttons = list(hold_snap.buttons)[:8]
        except Exception:
            hold_snap = None

        motion = 0.0
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
        except Exception:
            opt = None

        r2_now = float(hold_snap.r2) if hold_snap is not None else 0.0
        left_now = float(hold_snap.left) if hold_snap is not None else 0.0
        r2_onset = any(
            e.kind == "trigger" and str(e.name).upper() == "R2" for e in events
        )
        phrase, phrase_conf = "IDLE", 0.0
        try:
            from qoresence.sync.play_phrase import classify_phrase, phrase_payload

            phrase, phrase_conf = classify_phrase(
                r2=r2_now,
                prev_r2=float(getattr(self, "_prev_r2", 0.0) or 0.0),
                left=left_now,
                motion=motion,
                r2_onset_edge=r2_onset,
                video_age_s=age_s,
                hold_fresh=hold_energy > 0.0,
            )
            ph = phrase_payload(phrase, phrase_conf)
            if phrase in {"SNAP", "SPRINT"}:
                try:
                    from qoresence.vision.title_presence import request_lock_verify

                    request_lock_verify("phrase_snap" if phrase == "SNAP" else "phrase_sprint")
                except Exception:
                    pass
        except Exception:
            ph = {"phrase": "IDLE", "phrase_conf": 0.0, "phrase_live": False}
        self._prev_r2 = r2_now

        couple_tid = ""
        try:
            from qoresence.sync.coupling_ticket import get_coupling_book, mint_coupling_ticket
            from qoresence.sync.play_phrase import LIVE_PHRASES

            book = get_coupling_book()
            if ph.get("phrase") in LIVE_PHRASES and age_s <= 0.20:
                ticket = mint_coupling_ticket(
                    clock_ns=t_video,
                    frame_seq=seq,
                    phrase=str(ph["phrase"]),
                    coupling=coupling,
                    hold_energy=hold_energy,
                    imu_bodied=bool(any(e.imu_precursor_ms is not None for e in events)),
                )
                book.put(ticket)
                couple_tid = ticket.ticket_id if ticket is not None else ""
            else:
                book.expire()
        except Exception:
            couple_tid = ""

        payload = {
            "frame_seq": seq,
            "video_clock_ns": t_video,
            "input_events": len(events),
            "buttons": buttons,
            "input_energy": round(energy, 4),
            "edge_energy": round(edge_energy, 4),
            "hold_energy": round(hold_energy, 4),
            "coupling": round(coupling, 4),
            "coupling_ema": round(self._ema, 4),
            "lag_band_ms": [round(lag_lo_ms, 1), round(lag_hi_ms, 1)],
            "lead_ms": round(self.lead_ms, 1),
            "video_age_s": round(age_s, 3),
            "phrase": ph.get("phrase") or "IDLE",
            "phrase_conf": ph.get("phrase_conf") or 0.0,
            "coupling_ticket_id": couple_tid,
            # Two-speed ClutchBot: IVC is the realtime (fast) path signal
            "path": "fast",
        }
        if opt:
            payload["stick_gyro_r"] = opt.get("stick_gyro_r")
            payload["stick_motion_r"] = opt.get("stick_motion_r")
        prec_evs = [e for e in events if e.imu_precursor_ms is not None]
        if prec_evs:
            payload["imu_precursor_ms"] = round(
                sum(float(e.imu_precursor_ms or 0.0) for e in prec_evs) / len(prec_evs),
                2,
            )
            payload["imu_bodied"] = True
            payload["imu_precursor_name"] = str(prec_evs[-1].name)
        else:
            payload["imu_bodied"] = False
        try:
            from qoresence.sync.event_bind import get_event_binder

            binds = get_event_binder().recent()
            payload["binds"] = len(binds)
            if binds:
                last = binds[-1]
                payload["last_bind_ms"] = last.lag_ms
                payload["last_bind_kind"] = last.visual_kind
                payload["last_bind_hid"] = last.hid_name
        except Exception:
            payload["binds"] = 0
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
    lead_ms: float = DEFAULT_LEAD_MS,
    hz: float = DEFAULT_HZ,
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
            lead_ms=lead_ms,
            hz=hz,
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
            "edge_energy": 0.0,
            "hold_energy": 0.0,
            "coupling": 0.0,
            "coupling_ema": 0.0,
            "lag_band_ms": [DEFAULT_LAG_LO_MS, DEFAULT_LAG_HI_MS],
            "lead_ms": DEFAULT_LEAD_MS,
            "path": "fast",
            "imu_bodied": False,
            "binds": 0,
            "phrase": "IDLE",
            "phrase_conf": 0.0,
            "coupling_ticket_id": "",
        }
    out = ivc.get_last_coupling()
    out.setdefault("path", "fast")
    out.setdefault("imu_bodied", False)
    out.setdefault("binds", 0)
    out.setdefault("coupling_ema", out.get("coupling", 0.0))
    out.setdefault("hold_energy", 0.0)
    out.setdefault("edge_energy", 0.0)
    out.setdefault("phrase", "IDLE")
    out.setdefault("coupling_ticket_id", "")
    return out
