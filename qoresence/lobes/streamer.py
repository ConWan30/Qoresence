"""
Qoresence Streamer Lobe — Phase 3

UVC / OBS Virtual Cam capture with eye-check gate.
Emits activity, frame_stats, zone events onto RetinaEventBus.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from qoresence.core import (
    RetinaEventBus,
    SourceLobe,
    EventType,
    clock_ns,
    StreamerConfig,
)

log = logging.getLogger(__name__)


def _get_dshow_device_name(index: int) -> Optional[str]:
    """Return DirectShow display name for a device index, if available."""
    try:
        from pygrabber.dshow_graph import FilterGraph
        names = FilterGraph().get_input_devices()
        if 0 <= index < len(names):
            return names[index]
    except Exception as e:
        log.debug(f"Could not enumerate DShow device name: {e}")
    return None


def _is_allowed_capture_name(name: Optional[str]) -> bool:
    """
    Allow only external capture cards and virtual OBS output.
    Personal webcams / laptop cameras are rejected.
    """
    if not name:
        # Unknown source: only allow if we can later verify it is not a person
        return False
    n = name.lower()
    # Known disallowed words (laptop/personal cameras)
    if any(bad in n for bad in ["720p hd camera", "hd camera", "webcam", "integrated", "laptop", "facetime", "built-in"]):
        return any(good in n for good in ["usb3.0 video", "obs virtual"])
    # Known allowed sources
    if any(good in n for good in ["usb3.0 video", "obs virtual", "capture", "hdmi", "elgato", "avermedia", "usb video"]):
        return True
    # Any other "camera" is treated as a personal camera
    if "camera" in n:
        return False
    return True


def _frame_contains_person(frame: np.ndarray, area_threshold: float = 0.25) -> bool:
    """
    Lightweight person check on the first frame.
    Used as a safety net to avoid streaming a personal camera by mistake.
    """
    try:
        import mediapipe as mp
        from mediapipe.tasks.python.vision.object_detector import ObjectDetector, ObjectDetectorOptions
        from mediapipe.tasks.python.core.base_options import BaseOptions
        from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode

        # Re-use the same EfficientDet-Lite0 model that motion_tracker downloads
        from qoresence.vision.motion_tracker import MotionTracker
        model_path = MotionTracker._ensure_mediapipe_model()

        options = ObjectDetectorOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=VisionTaskRunningMode.IMAGE,
            max_results=5,
            score_threshold=0.3,
        )
        detector = ObjectDetector.create_from_options(options)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        results = detector.detect(mp_image)

        h, w = frame.shape[:2]
        frame_area = h * w
        for det in results.detections:
            category = det.categories[0].category_name.lower()
            if category == "person":
                bbox = det.bounding_box
                box_area = bbox.width * bbox.height
                if box_area / frame_area > area_threshold:
                    return True
        return False
    except Exception as e:
        log.debug(f"Person guard check failed: {e}")
        # If we cannot verify, fail-safe: assume person present
        return True


# ──────────────────────────────────────────────────────────────────────────────
# ZONE DEFINITIONS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ZoneSpec:
    """Zone specification for HUD monitoring."""
    zone_id: str
    # Normalized ROI: x, y, width, height in [0, 1]
    x: float
    y: float
    width: float
    height: float
    threshold: float = 12.0  # Mean absolute luma delta vs EMA baseline


DEFAULT_ZONES = (
    ZoneSpec("hud_scoreboard", 0.25, 0.0, 0.5, 0.12, threshold=10.0),
    ZoneSpec("hud_bottom", 0.15, 0.85, 0.7, 0.15, threshold=10.0),
)


# ──────────────────────────────────────────────────────────────────────────────
# STREAMER RUNTIME
# ──────────────────────────────────────────────────────────────────────────────

class StreamerRuntime:
    """
    Main capture loop: grab frames → metrics → events → RetinaEventBus.

    Runs in a background thread. All events carry session_id + clock_ns + source_lobe.
    """

    def __init__(
        self,
        config: StreamerConfig,
        bus: RetinaEventBus,
        session_head_ns: int,
        presence_touch_file: Optional[Path] = None,
        presence_timeout_s: float = 5.0,
    ):
        self.config = config
        self.bus = bus
        self.session_head_ns = session_head_ns

        # Presence sync (WP-S5): reads touch file mtime updated by controller lobe
        self.presence_touch_file = presence_touch_file
        self.presence_timeout_s = presence_timeout_s

        # Capture state
        self._cap: Optional[cv2.VideoCapture] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Metrics state
        self._prev_gray: Optional[np.ndarray] = None
        self._activity = "idle"
        self._activity_since = 0.0
        self._zone_emas: dict[str, float] = {}
        self._zone_states: dict[str, str] = {}
        self._frames_processed = 0
        self._start_time = 0.0

        # Eye-check
        self._eye_check_done = False
        self._eye_check_snapshot_path: Optional[Path] = None

        # Zone configs
        self._zones = DEFAULT_ZONES if config.zones_enabled else ()

        # Current frame (for cross-lobe integration)
        self._current_frame: Optional[np.ndarray] = None

        # Presence callback (for fusion engine)
        self._presence_callback: Optional[callable] = None

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Open capture device and start background thread."""
        if self._running:
            log.warning("StreamerRuntime already running")
            return True

        # Open capture device
        if not self._open_capture():
            return False

        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._run_loop, name="qoresence-streamer", daemon=True)
        self._thread.start()

        source = self.config.url if self.config.source_kind == "network" else self.config.device_index
        log.info(f"Streamer lobe started: source={source}, "
                 f"source_kind={self.config.source_kind}, fps={self.config.fps_target}")
        return True

    def stop(self) -> None:
        """Stop capture thread and release device."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        log.info("Streamer lobe stopped")

    def is_running(self) -> bool:
        return self._running

    def get_current_frame(self) -> Optional[np.ndarray]:
        """Get the most recent captured frame (for cross-lobe integration)."""
        return self._current_frame

    def set_presence_callback(self, callback: callable) -> None:
        """Set callback for presence status updates (for fusion engine)."""
        self._presence_callback = callback

    # ──────────────────────────────────────────────────────────────────────────
    # CAPTURE DEVICE
    # ──────────────────────────────────────────────────────────────────────────

    def _open_capture(self) -> bool:
        """Open UVC device or network stream with backend selection."""
        backend = self.config.backend.lower()
        backend_flag = None

        is_network = self.config.source_kind == "network" and self.config.url

        if backend == "msmf" and not is_network:
            backend_flag = cv2.CAP_MSMF
        elif backend == "dshow" and not is_network:
            backend_flag = cv2.CAP_DSHOW
        # "auto" = no flag

        try:
            if is_network:
                log.info(f"Opening network stream: {self.config.url}")
                self._cap = cv2.VideoCapture(self.config.url)
            elif backend_flag is not None:
                self._cap = cv2.VideoCapture(self.config.device_index, backend_flag)
            else:
                self._cap = cv2.VideoCapture(self.config.device_index)

            if not self._cap.isOpened():
                source = self.config.url if is_network else self.config.device_index
                log.error(f"Failed to open capture source {source}")
                return False

            if not is_network:
                # Set resolution and FPS only for local devices
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
                self._cap.set(cv2.CAP_PROP_FPS, self.config.fps_target)

            # Verify first frame
            ok, frame = self._cap.read()
            if not ok or frame is None:
                log.error("First frame read failed")
                self._cap.release()
                return False

            # Privacy / device-name guard for local capture devices
            if not is_network and os.environ.get("QORESENCE_PRIVACY_GUARD", "1") != "0":
                device_name = _get_dshow_device_name(self.config.device_index)
                if not _is_allowed_capture_name(device_name):
                    log.error(
                        f"PRIVACY GUARD: device index {self.config.device_index} "
                        f"is '{device_name}'. This looks like a personal camera. Capture refused."
                    )
                    self._cap.release()
                    self._cap = None
                    return False

                # Secondary person-area guard to catch mis-configured sources
                if self.config.eye_check_required and _frame_contains_person(frame):
                    log.error(
                        f"PRIVACY GUARD: first frame from {device_name} contains a person. "
                        "This is not a game feed. Capture refused."
                    )
                    self._cap.release()
                    self._cap = None
                    return False

            # Eye-check: save first frame for operator verification
            if self.config.eye_check_required:
                self._save_eye_check_snapshot(frame)

            log.info(f"Capture opened: {frame.shape[1]}x{frame.shape[0]} @ "
                     f"{self._cap.get(cv2.CAP_PROP_FPS):.1f} FPS (requested {self.config.fps_target})")
            return True

        except Exception as e:
            log.error(f"Capture open failed: {e}")
            if self._cap:
                self._cap.release()
            return False

    def _save_eye_check_snapshot(self, frame: np.ndarray) -> None:
        """Save first frame for mandatory eye-check."""
        if self.config.snapshot_path:
            path = Path(self.config.snapshot_path)
        else:
            path = Path.cwd() / "logs" / f"eye_check_{self.session_head_ns}.png"

        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), frame)
        self._eye_check_snapshot_path = path
        log.warning(f"EYE-CHECK REQUIRED: Verify {path} shows GAME, not webcam/black HDCP")

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN LOOP
    # ──────────────────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Background capture loop."""
        period = 1.0 / max(self.config.fps_target, 1.0)
        last_stats = 0.0
        last_heartbeat = 0.0

        # Emit session_start
        self._emit_session_start()

        while self._running:
            loop_start = time.time()

            # Grab frame
            ok, frame = self._cap.read() if self._cap else (False, None)
            if not ok or frame is None:
                time.sleep(0.01)
                continue

            self._frames_processed += 1

            # Store current frame for cross-lobe integration
            self._current_frame = frame

            # Downscale for metrics
            scale = self.config.process_scale
            if scale < 1.0:
                frame_s = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            else:
                frame_s = frame

            gray = cv2.cvtColor(frame_s, cv2.COLOR_BGR2GRAY)
            now = time.time()

            # Process metrics
            self._process_frame(gray, now)

            # Periodic frame_stats
            if now - last_stats >= self.config.stats_every_s:
                self._emit_frame_stats(now)
                last_stats = now

            # Heartbeat
            if now - last_heartbeat >= self.config.heartbeat_every_s:
                self._emit_heartbeat(now)
                last_heartbeat = now

            # Pace
            elapsed = time.time() - loop_start
            sleep_time = period - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Session end
        self._emit_session_end()

    # ──────────────────────────────────────────────────────────────────────────
    # METRICS PROCESSING
    # ──────────────────────────────────────────────────────────────────────────

    def _process_frame(self, gray: np.ndarray, now: float) -> None:
        """Compute motion, activity, zones from frame."""
        # Motion (mean absolute difference)
        motion = 0.0
        if self._prev_gray is not None:
            motion = float(np.mean(np.abs(gray.astype(np.float32) - self._prev_gray.astype(np.float32))))
        self._prev_gray = gray.copy()

        mean_luma = float(np.mean(gray))

        # Activity with hysteresis
        desired = "idle"
        if motion >= self.config.motion_high:
            desired = "high"
        elif motion >= self.config.motion_low:
            desired = "low"

        if desired != self._activity:
            if now - self._activity_since >= self.config.activity_hysteresis_s:
                prev = self._activity
                self._activity = desired
                self._activity_since = now
                self._emit_activity(now, motion, mean_luma, prev)
            else:
                self._activity_since = now  # Reset timer on change
        elif desired == self._activity:
            self._activity_since = now  # Keep extending hold

        # Zones
        for zone in self._zones:
            self._process_zone(gray, zone, now)

    def _process_zone(self, gray: np.ndarray, zone: ZoneSpec, now: float) -> None:
        """Process a single zone for activity detection."""
        h, w = gray.shape[:2]
        x0 = max(0, min(w - 1, int(zone.x * w)))
        y0 = max(0, min(h - 1, int(zone.y * h)))
        x1 = max(x0 + 1, min(w, int((zone.x + zone.width) * w)))
        y1 = max(y0 + 1, min(h, int((zone.y + zone.height) * h)))

        crop = gray[y0:y1, x0:x1]
        if crop.size == 0:
            return

        zone_luma = float(np.mean(crop))
        ema = self._zone_emas.get(zone.zone_id)

        if ema is None:
            self._zone_emas[zone.zone_id] = zone_luma
            self._zone_states[zone.zone_id] = "quiet"
            return

        delta = abs(zone_luma - ema)
        # Slow EMA
        self._zone_emas[zone.zone_id] = 0.95 * ema + 0.05 * zone_luma

        state = "active" if delta >= zone.threshold else "quiet"
        prev = self._zone_states.get(zone.zone_id, "quiet")

        if state != prev:
            self._zone_states[zone.zone_id] = state
            self._emit_zone(zone.zone_id, state, prev, delta, zone_luma, now)

    # ──────────────────────────────────────────────────────────────────────────
    # EVENT EMISSION
    # ──────────────────────────────────────────────────────────────────────────

    def _emit_session_start(self) -> None:
        """Emit session_start event."""
        payload = {
            "jsonl": str(self.bus.jsonl_path) if self.bus.jsonl_path else None,
            "ws": f"ws://{self.bus.ws_host}:{self.bus.ws_port}" if self.bus.enable_ws else None,
            "advisory": True,
            "note": "optical events are not humanity or tournament proof",
            "source_kind": self.config.source_kind,
            "device_index": self.config.device_index,
            "device_name": self.config.device_name,
        }
        if self._eye_check_snapshot_path:
            payload["eye_check_snapshot"] = str(self._eye_check_snapshot_path)

        self.bus.emit_raw(
            source_lobe=SourceLobe.STREAMER,
            event_type="session_start",
            payload=payload,
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    def _emit_activity(self, now: float, motion: float, mean_luma: float, prev: str) -> None:
        """Emit activity transition event."""
        presence_sync, last_ago = self._check_presence(now)

        self.bus.emit_raw(
            source_lobe=SourceLobe.STREAMER,
            event_type="activity",
            payload={
                "level": self._activity,
                "prev": prev,
                "motion": round(motion, 3),
                "mean_luma": round(mean_luma, 2),
                "presence_sync_ok": presence_sync,
                "last_controller_s_ago": round(last_ago, 3) if last_ago is not None else None,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

        # Call presence callback for fusion engine
        if self._presence_callback:
            try:
                self._presence_callback({
                    "lobe": "streamer",
                    "presence_sync_ok": presence_sync,
                    "activity": self._activity,
                    "motion": motion,
                })
            except Exception:
                pass

    def _emit_zone(self, zone_id: str, state: str, prev: str, delta: float, luma: float, now: float) -> None:
        """Emit zone state change event."""
        presence_sync, last_ago = self._check_presence(now)

        self.bus.emit_raw(
            source_lobe=SourceLobe.STREAMER,
            event_type="zone",
            payload={
                "zone_id": zone_id,
                "state": state,
                "prev": prev,
                "delta": round(delta, 3),
                "luma": round(luma, 2),
                "presence_sync_ok": presence_sync,
                "last_controller_s_ago": round(last_ago, 3) if last_ago is not None else None,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    def _emit_frame_stats(self, now: float) -> None:
        """Emit periodic frame statistics."""
        elapsed = max(now - self._start_time, 1e-6)
        presence_sync, last_ago = self._check_presence(now)

        self.bus.emit_raw(
            source_lobe=SourceLobe.STREAMER,
            event_type="frame_stats",
            payload={
                "n": self._frames_processed,
                "fps_meas": round(self._frames_processed / elapsed, 2),
                "mean_luma": round(float(np.mean(self._prev_gray)) if self._prev_gray is not None else 0, 2),
                "motion": round(
                    float(np.mean(np.abs(self._prev_gray.astype(np.float32) - self._prev_gray.astype(np.float32)))) if self._prev_gray is not None else 0, 3
                ),
                "activity": self._activity,
                "presence_sync_ok": presence_sync,
                "last_controller_s_ago": round(last_ago, 3) if last_ago is not None else None,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    def _emit_heartbeat(self, now: float) -> None:
        """Emit heartbeat for liveness."""
        self.bus.emit_raw(
            source_lobe=SourceLobe.STREAMER,
            event_type="heartbeat",
            payload={
                "uptime_s": round(now - self._start_time, 1),
                "frames": self._frames_processed,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    def _emit_session_end(self) -> None:
        """Emit session_end summary."""
        elapsed = max(time.time() - self._start_time, 1e-6)
        self.bus.emit_raw(
            source_lobe=SourceLobe.STREAMER,
            event_type="session_end",
            payload={
                "frames": self._frames_processed,
                "events": self.bus.events_emitted,
                "elapsed_s": round(elapsed, 2),
                "fps_meas": round(self._frames_processed / elapsed, 2),
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # PRESENCE SYNC (WP-S5)
    # ──────────────────────────────────────────────────────────────────────────

    def _check_presence(self, now: float) -> tuple[bool, Optional[float]]:
        """
        Check if controller input was recent (via touch file).

        Returns (presence_sync_ok, seconds_since_last_input).
        """
        if not self.presence_touch_file or not self.presence_touch_file.exists():
            return False, None

        try:
            last_input = self.presence_touch_file.stat().st_mtime
            ago = now - last_input
            return ago <= self.presence_timeout_s, ago
        except Exception:
            return False, None