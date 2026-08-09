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
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from qoresence.core import (
    RetinaEventBus,
    SourceLobe,
    StreamerConfig,
    clock_ns,
)

log = logging.getLogger(__name__)


def _get_dshow_device_name(index: int) -> str | None:
    """Return DirectShow display name for a device index, if available."""
    try:
        from pygrabber.dshow_graph import FilterGraph

        names = FilterGraph().get_input_devices()
        if 0 <= index < len(names):
            return names[index]
    except Exception as e:
        log.debug(f"Could not enumerate DShow device name: {e}")
    return None


def _is_obs_virtual_camera_name(name: str | None) -> bool:
    """True if device name looks like OBS Virtual Camera (Pattern A source)."""
    if not name:
        return False
    n = name.lower()
    return "obs virtual" in n or n.strip() in {"obs-camera", "obs camera"}


def list_dshow_devices() -> list[tuple[int, str, bool, str]]:
    """Enumerate DirectShow input devices with allowed/blocked status.

    Returns a list of (index, name, is_allowed, backend) tuples.
    Backend is ``dshow`` for pygrabber enumeration (Windows pilot).
    """
    try:
        from pygrabber.dshow_graph import FilterGraph

        names = FilterGraph().get_input_devices()
    except Exception as e:
        log.warning(f"Could not enumerate DShow devices: {e}")
        return []
    return [
        (i, name, _is_allowed_capture_name(name), "dshow")
        for i, name in enumerate(names)
    ]


# Physical HDMI capture card name hints (order = preference)
_PHYSICAL_CARD_HINTS = (
    "usb3.0 video",
    "usb 3.0 video",
    "usb video",
    "elgato",
    "avermedia",
    "capture",
    "hdmi",
    "game capture",
    "live gamer",
)


def _is_physical_card_name(name: str | None) -> bool:
    """True for real capture hardware (not webcam, not OBS VCam)."""
    if not name or not _is_allowed_capture_name(name):
        return False
    if _is_obs_virtual_camera_name(name):
        return False
    n = name.lower()
    if any(h in n for h in _PHYSICAL_CARD_HINTS):
        return True
    # Allowed non-camera device without "camera" in the name
    return "camera" not in n


def resolve_capture_device(
    requested_index: int | None = None,
    *,
    prefer_name: str | None = None,
    allow_obs_vcam: bool = False,
) -> tuple[int, str] | None:
    """Pick a capture device that survives unplug/replug index shifts.

    Priority:
      1. Exact ``prefer_name`` match (sticky name from last good open)
      2. Physical card hints (USB3.0 Video, Elgato, …)
      3. ``requested_index`` if still allowed / physical
      4. OBS Virtual Camera only if ``allow_obs_vcam``

    Returns ``(index, name)`` or None if nothing suitable is present.
    """
    devices = list_dshow_devices()
    if not devices:
        return None

    # 1) Sticky preferred name (case-insensitive exact or contains)
    if prefer_name:
        pn = prefer_name.strip().lower()
        for idx, name, allowed, _be in devices:
            if not allowed:
                continue
            nl = name.lower()
            if nl == pn or pn in nl or nl in pn:
                return int(idx), name

    # 2) Physical capture cards
    physical = [
        (int(idx), name)
        for idx, name, allowed, _be in devices
        if allowed and _is_physical_card_name(name)
    ]
    if physical:
        # Prefer USB3.0 Video explicitly when multiple cards
        for idx, name in physical:
            if "usb3.0" in name.lower() or "usb 3.0" in name.lower():
                return idx, name
        return physical[0]

    # 3) Requested index if still valid and allowed
    if requested_index is not None and requested_index >= 0:
        for idx, name, allowed, _be in devices:
            if int(idx) == int(requested_index) and allowed:
                if allow_obs_vcam or not _is_obs_virtual_camera_name(name):
                    return int(idx), name

    # 4) Optional VCam
    if allow_obs_vcam:
        for idx, name, allowed, _be in devices:
            if allowed and _is_obs_virtual_camera_name(name):
                return int(idx), name

    return None


def _is_allowed_capture_name(name: str | None) -> bool:
    """
    Allow only external capture cards and virtual OBS output.
    Personal webcams / laptop cameras are rejected.
    """
    if not name:
        # Unknown source: only allow if we can later verify it is not a person
        return False
    n = name.lower()
    # Known disallowed words (laptop/personal cameras)
    if any(
        bad in n
        for bad in [
            "720p hd camera",
            "hd camera",
            "webcam",
            "integrated",
            "laptop",
            "facetime",
            "built-in",
        ]
    ):
        return any(good in n for good in ["usb3.0 video", "obs virtual"])
    # Known allowed sources
    if any(
        good in n
        for good in [
            "usb3.0 video",
            "obs virtual",
            "capture",
            "hdmi",
            "elgato",
            "avermedia",
            "usb video",
        ]
    ):
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
        from mediapipe.tasks.python.core.base_options import BaseOptions
        from mediapipe.tasks.python.vision.core.vision_task_running_mode import (
            VisionTaskRunningMode,
        )
        from mediapipe.tasks.python.vision.object_detector import (
            ObjectDetector,
            ObjectDetectorOptions,
        )

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
        presence_touch_file: Path | None = None,
        presence_timeout_s: float = 5.0,
    ):
        self.config = config
        self.bus = bus
        self.session_head_ns = session_head_ns

        # Presence sync (WP-S5): reads touch file mtime updated by controller lobe
        self.presence_touch_file = presence_touch_file
        self.presence_timeout_s = presence_timeout_s

        # Capture state
        self._cap: cv2.VideoCapture | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        # Sticky device name so unplug/replug rebinds even if DShow index shifts
        self._preferred_device_name: str | None = getattr(config, "device_name", None)
        self._bound_device_name: str | None = None
        self._last_rebind_attempt = 0.0
        # Dedicated grabber — DShow read never blocks the process/LIVE path
        self._grab_thread: threading.Thread | None = None
        self._grab_stop = threading.Event()
        self._grab_lock = threading.Lock()
        self._grab_latest: np.ndarray | None = None
        self._grab_ts: float = 0.0
        self._grab_alive = False

        # Metrics state
        self._prev_gray: np.ndarray | None = None
        self._activity = "idle"
        self._activity_since = 0.0
        self._zone_emas: dict[str, float] = {}
        self._zone_states: dict[str, str] = {}
        self._frames_processed = 0
        self._start_time = 0.0
        self._last_motion = 0.0

        # Hardening: FPS fallback + watchdog liveness
        self._effective_fps = float(config.fps_target)
        self._fps_changed = False
        self._consecutive_failures = 0
        self._last_success_frame_time = time.time()
        self._fps_window: deque[float] = deque(maxlen=max(int(config.fps_target), 15))
        self._watchdog_running = False
        self._watchdog_thread: threading.Thread | None = None
        self._lock = threading.RLock()

        # Eye-check
        self._eye_check_done = False
        self._eye_check_snapshot_path: Path | None = None

        # Zone configs
        self._zones = DEFAULT_ZONES if config.zones_enabled else ()

        # Current frame (for cross-lobe integration)
        self._current_frame: np.ndarray | None = None

        # Presence callback (for fusion engine)
        self._presence_callback: callable | None = None

        # Pattern A detection (OBS Virtual Cam → higher lag)
        self._is_pattern_a = False
        self._pattern_a_lag_samples: deque[float] = deque(maxlen=30)
        self._pattern_a_hint_logged = False

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Open capture device and start background thread.

        If the physical card is unplugged, still starts and hotplug-rebinds when
        USB3.0 Video reappears (index may change).
        """
        if self._running:
            log.warning("StreamerRuntime already running")
            return True

        # Open capture device — tolerate missing card (wait for replug)
        opened = self._open_capture()
        if not opened:
            is_network = self.config.source_kind == "network" and self.config.url
            if is_network:
                return False
            log.warning(
                "Capture card not open yet (unplugged or busy). "
                "Streamer will hotplug-rebind when USB3.0 Video appears. "
                "List: python -m qoresence.cli --streamer-list"
            )

        self._running = True
        self._start_time = time.time()
        self._last_success_frame_time = self._start_time
        self._thread = threading.Thread(
            target=self._run_loop, name="qoresence-streamer", daemon=True
        )
        self._thread.start()

        # Watchdog heartbeat prevents fusion temporal_desync when cap.read() blocks.
        self._watchdog_running = True
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="qoresence-streamer-watchdog", daemon=True
        )
        self._watchdog_thread.start()

        source = (
            self.config.url if self.config.source_kind == "network" else self.config.device_index
        )
        log.info(
            f"Streamer lobe started: source={source}, "
            f"source_kind={self.config.source_kind}, fps_target={self._effective_fps:.1f}, "
            f"opened={opened}, sticky_name={self._preferred_device_name!r}"
        )
        return True

    def stop(self) -> None:
        """Stop capture thread, watchdog, and release device."""
        self._running = False
        self._watchdog_running = False
        self._stop_grabber()
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=1.0)
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        log.info("Streamer lobe stopped")

    def is_running(self) -> bool:
        return self._running

    def get_current_frame(self) -> np.ndarray | None:
        """Get the most recent captured frame (for cross-lobe integration)."""
        return self._current_frame

    def set_presence_callback(self, callback: callable) -> None:
        """Set callback for presence status updates (for fusion engine)."""
        self._presence_callback = callback

    # ──────────────────────────────────────────────────────────────────────────
    # CAPTURE DEVICE
    # ──────────────────────────────────────────────────────────────────────────

    def _resolve_device(self) -> tuple[int, str] | None:
        """Resolve current DShow index by sticky name / physical card preference."""
        allow_vcam = os.environ.get("QORESENCE_ALLOW_OBS_VCAM", "0").strip() in {
            "1",
            "true",
            "yes",
        }
        prefer = self._preferred_device_name or getattr(self.config, "device_name", None)
        # --streamer-device -1 means full auto; otherwise try requested then rebind
        req = int(getattr(self.config, "device_index", 0) or 0)
        if req < 0:
            req = None
        resolved = resolve_capture_device(
            req,
            prefer_name=prefer,
            allow_obs_vcam=allow_vcam,
        )
        if resolved is None and req is not None:
            # Explicit index pointed at webcam after unplug — fall back to any physical
            resolved = resolve_capture_device(
                None, prefer_name=prefer, allow_obs_vcam=allow_vcam
            )
        return resolved

    def _open_capture(self) -> bool:
        """Open UVC device or network stream with backend selection.

        Re-resolves the physical card by name so unplug/replug index shifts work.
        """
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
                device_name = None
            else:
                resolved = self._resolve_device()
                if resolved is None:
                    log.error(
                        "No capture card found (USB3.0 Video / HDMI unplugged?). "
                        "Replug the card and restart, or wait for hotplug rebind. "
                        "List: python -m qoresence.cli --streamer-list"
                    )
                    return False
                idx, device_name = resolved
                if idx != int(getattr(self.config, "device_index", -1) or -1):
                    log.info(
                        "Capture device rebound: idx %s → %s (%r)",
                        getattr(self.config, "device_index", None),
                        idx,
                        device_name,
                    )
                # Update runtime config index (frozen dataclass → object setattr best-effort)
                try:
                    object.__setattr__(self.config, "device_index", idx)
                except Exception:
                    pass
                self._bound_device_name = device_name
                if _is_physical_card_name(device_name):
                    self._preferred_device_name = device_name
                if backend_flag is not None:
                    self._cap = cv2.VideoCapture(idx, backend_flag)
                else:
                    self._cap = cv2.VideoCapture(idx)

            if not self._cap.isOpened():
                source = self.config.url if is_network else (
                    f"{self.config.device_index} ({device_name})"
                )
                log.error(f"Failed to open capture source {source}")
                if not is_network:
                    log.error(
                        "Device busy/unplugged — replug USB3.0 Video, or if OBS holds "
                        "the card use Virtual Cam (legacy). See docs/OBS_OWNS_CARD.md"
                    )
                return False

            if not is_network and _is_obs_virtual_camera_name(device_name):
                self._is_pattern_a = True
                log.info(
                    "streamer source: OBS Virtual Camera (OBS owns physical card) idx=%s name=%r",
                    self.config.device_index,
                    device_name,
                )
                log.info(
                    "capture ownership: Pattern A (OBS owns card → Virtual Cam → Qoresence). "
                    "Higher lag for monitor/OCR. See docs/CAPTURE_OWNERSHIP.md"
                )
            elif not is_network:
                log.info(
                    "streamer source: physical card idx=%s name=%r (sticky name for replug)",
                    self.config.device_index,
                    device_name,
                )
                log.info(
                    "capture ownership: Pattern B (Qoresence owns card). "
                    "OBS must not open this DShow device. See docs/CAPTURE_OWNERSHIP.md"
                )

            if not is_network:
                # Set resolution and FPS only for local devices
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
                self._cap.set(cv2.CAP_PROP_FPS, self.config.fps_target)

            # Verify first frame (with timeout so a frozen device can’t block open)
            ok, frame = self._timed_read(self._cap, timeout=2.0)
            if not ok or frame is None:
                log.error("First frame read failed")
                if not is_network and not _is_obs_virtual_camera_name(device_name):
                    log.error(
                        "Device busy or still enumerating after plug — will retry rebind."
                    )
                self._cap.release()
                self._cap = None
                return False

            # Privacy / device-name guard for local capture devices
            if not is_network and os.environ.get("QORESENCE_PRIVACY_GUARD", "1") != "0":
                if device_name is None:
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
                # Skip for known physical cards (logo faces on pause menus false-positive)
                if (
                    self.config.eye_check_required
                    and not _is_physical_card_name(device_name)
                    and _frame_contains_person(frame)
                ):
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

            log.info(
                f"Capture opened: {frame.shape[1]}x{frame.shape[0]} @ "
                f"{self._cap.get(cv2.CAP_PROP_FPS):.1f} FPS (requested {self.config.fps_target})"
            )
            # Use Grok timeout-based read in the main loop instead of a dedicated
            # grabber thread — the grabber thread can hold a dead DShow filter and
            # prevent rebind (commit 723e84f reintroduced this failure mode).
            log.info("Capture opened (Grok timeout read, no grabber thread)")
            return True

        except Exception as e:
            log.error(f"Capture open failed: {e}")
            if not is_network:
                log.error(
                    "Replug capture card or free it from OBS. "
                    "List: python -m qoresence.cli --streamer-list"
                )
            self._stop_grabber()
            if self._cap:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None
            return False

    def _start_grabber(self) -> None:
        """Background thread: only job is cap.read() → latest slot."""
        self._stop_grabber()
        self._grab_stop.clear()
        self._grab_alive = True

        def _loop() -> None:
            fail = 0
            while not self._grab_stop.is_set():
                cap = self._cap
                if cap is None:
                    time.sleep(0.05)
                    continue
                try:
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        with self._grab_lock:
                            # no copy here — consumer copies
                            self._grab_latest = frame
                            self._grab_ts = time.monotonic()
                        fail = 0
                    else:
                        fail += 1
                        if fail > 30:
                            time.sleep(0.02)
                        else:
                            time.sleep(0.001)
                except Exception as e:
                    fail += 1
                    log.debug("grabber read: %s", e)
                    time.sleep(0.02)
            self._grab_alive = False

        self._grab_thread = threading.Thread(
            target=_loop, name="qoresence-dshow-grab", daemon=True
        )
        self._grab_thread.start()
        log.info("Capture grabber thread started (non-blocking LIVE path)")

    def _stop_grabber(self) -> None:
        self._grab_stop.set()
        t = self._grab_thread
        if t is not None and t.is_alive():
            t.join(timeout=1.5)
        self._grab_thread = None
        with self._grab_lock:
            self._grab_latest = None
            self._grab_ts = 0.0
        self._grab_alive = False

    def _try_rebind_capture(self) -> bool:
        """Hotplug: re-enumerate DShow and reopen preferred physical card."""
        now = time.time()
        if now - self._last_rebind_attempt < 3.0:
            return False
        self._last_rebind_attempt = now
        if self.config.source_kind == "network" and self.config.url:
            return False
        resolved = self._resolve_device()
        if resolved is None:
            log.warning(
                "Capture rebind: no physical card yet (unplugged). Waiting for USB3.0 Video…"
            )
            return False
        idx, name = resolved
        log.info("Capture rebind attempting idx=%s name=%r", idx, name)
        self._stop_grabber()
        try:
            if self._cap is not None:
                self._cap.release()
                self._cap = None
        except Exception:
            self._cap = None
        try:
            object.__setattr__(self.config, "device_index", idx)
        except Exception:
            pass
        ok = self._open_capture()
        if ok:
            log.info("Capture rebind OK — idx=%s name=%r", idx, name)
        return ok

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
        """Background capture loop with retry and FPS fallback."""
        last_stats = 0.0
        last_heartbeat = 0.0

        # Emit session_start
        self._emit_session_start()

        while self._running:
            loop_start = time.time()

            # Apply any FPS change requested by the watchdog
            with self._lock:
                if self._fps_changed and self._cap is not None:
                    try:
                        self._cap.set(cv2.CAP_PROP_FPS, self._effective_fps)
                    except Exception:
                        pass
                    self._fps_changed = False
                    self._emit_degraded_notice(loop_start)

            # Grab frame with retry
            ok, frame = self._read_frame()
            if not ok or frame is None:
                with self._lock:
                    self._consecutive_failures += 1
                    fails = self._consecutive_failures
                # Hotplug: card unplugged or index shifted after replug
                if fails >= 30 or self._cap is None:
                    if self._try_rebind_capture():
                        with self._lock:
                            self._consecutive_failures = 0
                        continue
                time.sleep(0.05 if fails > 5 else 0.001)
                continue

            with self._lock:
                self._consecutive_failures = 0
                self._last_success_frame_time = time.time()
                self._fps_window.append(time.time())

            self._frames_processed += 1

            # Store current frame for cross-lobe integration
            self._current_frame = frame
            # Rolling HDMI buffer for local Foundry / ClutchBot clips (true capture card)
            try:
                from qoresence.vision.clip_buffer import push_frame as _clip_push

                _clip_push(frame)
            except Exception:
                pass
            # FrameHub for monitor + IVC (same frames — never second capture)
            try:
                from qoresence.monitor.frame_hub import publish as _hub_publish

                _hub_publish(frame, clock_ns=clock_ns())
            except Exception:
                pass

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

            # Pattern A lag auto-tune: measure inter-frame delta and log hints
            if self._is_pattern_a:
                self._pattern_a_lag_samples.append(now)
                if (
                    not self._pattern_a_hint_logged
                    and len(self._pattern_a_lag_samples) >= 20
                ):
                    samples = list(self._pattern_a_lag_samples)
                    deltas = [samples[i] - samples[i - 1] for i in range(1, len(samples))]
                    avg_delta = sum(deltas) / len(deltas) if deltas else 0
                    expected = 1.0 / max(1.0, self._effective_fps)
                    lag_ratio = avg_delta / expected if expected > 0 else 1.0
                    if lag_ratio > 1.5:
                        log.warning(
                            "Pattern A lag hint: avg inter-frame %.0fms vs expected %.0fms "
                            "(%.1fx slower). Consider Pattern B (Qoresence owns card) "
                            "for lower latency. See docs/OBS_OWNS_CARD.md",
                            avg_delta * 1000,
                            expected * 1000,
                            lag_ratio,
                        )
                    else:
                        log.info(
                            "Pattern A lag OK: avg inter-frame %.0fms vs expected %.0fms",
                            avg_delta * 1000,
                            expected * 1000,
                        )
                    self._pattern_a_hint_logged = True

            # Periodic frame_stats
            if now - last_stats >= self.config.stats_every_s:
                self._emit_frame_stats(now)
                last_stats = now

            # Heartbeat
            if now - last_heartbeat >= self.config.heartbeat_every_s:
                self._emit_heartbeat(now)
                last_heartbeat = now

            # Pace
            with self._lock:
                period = 1.0 / max(self._effective_fps, 1.0)
            elapsed = time.time() - loop_start
            sleep_time = period - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Session end
        self._emit_session_end()

    def _read_frame(self) -> tuple[bool, np.ndarray | None]:
        """Read a frame with a hard timeout so DShow hangs cannot freeze LIVE forever.

        Original Grok fix (commit fb47f29): cap.read() runs in a short-lived
        daemon thread with a 1.25s join. If it hangs, release the capture device
        and set self._cap = None so the main loop will rebind.
        """
        if self._cap is None:
            return False, None
        ok, frame = self._timed_read(self._cap, timeout=1.25)
        if ok and frame is not None:
            return True, np.ascontiguousarray(frame)
        return False, None

    def _timed_read(self, cap: Any, timeout: float = 1.25) -> tuple[bool, np.ndarray | None]:
        """Run cap.read() in a daemon thread with a timeout."""
        box: list[Any] = []

        def _grab() -> None:
            try:
                ok, frame = cap.read()
                box.append((bool(ok), frame))
            except Exception:
                box.append((False, None))

        t = threading.Thread(target=_grab, name="dshow-grab", daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            log.warning("cap.read() timed out (>%.2fs) — forcing rebind", timeout)
            try:
                cap.release()
            except Exception:
                pass
            with self._lock:
                self._cap = None
                self._consecutive_failures = 99
            return False, None
        if not box:
            return False, None
        ok, frame = box[-1]
        if ok and frame is not None:
            return True, np.ascontiguousarray(frame)
        return False, None

    def _watchdog_loop(self) -> None:
        """Watchdog thread: emit heartbeat and degrade FPS if frames stall."""
        while self._watchdog_running and self._running:
            now = time.time()
            with self._lock:
                stall_s = now - self._last_success_frame_time
                # Emit a streamer heartbeat every second so fusion never sees >5s silence
                self._emit_heartbeat(now)

                # If no successful frame for >1.5s, lower requested FPS to ease USB load
                if stall_s > 1.5 and self._effective_fps > 15.0:
                    new_fps = max(15.0, self._effective_fps / 2)
                    log.warning(
                        f"Streamer stalled {stall_s:.1f}s; lowering fps_target "
                        f"{self._effective_fps:.1f} -> {new_fps:.1f}"
                    )
                    self._effective_fps = new_fps
                # Longer stall (unplug) — kick rebind so replug picks new index
                if stall_s > 4.0:
                    try:
                        self._try_rebind_capture()
                    except Exception as e:
                        log.debug("watchdog rebind: %s", e)
                    self._fps_changed = True

            time.sleep(1.0)

    def _emit_degraded_notice(self, now: float) -> None:
        """Emit a frame_stats event noting the FPS fallback."""
        self.bus.emit_raw(
            source_lobe=SourceLobe.STREAMER,
            event_type="frame_stats",
            payload={
                "n": self._frames_processed,
                "fps_meas": round(self._measure_actual_fps(), 2),
                "mean_luma": round(
                    float(np.mean(self._prev_gray)) if self._prev_gray is not None else 0, 2
                ),
                "motion": round(self._last_motion, 3),
                "activity": self._activity,
                "presence_sync_ok": self._check_presence(now)[0],
                "last_controller_s_ago": round(self._check_presence(now)[1], 3)
                if self._check_presence(now)[1] is not None
                else None,
                "degraded": True,
                "fps_target": round(self._effective_fps, 1),
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    def _measure_actual_fps(self) -> float:
        """Compute actual FPS over the last window of successful frame times."""
        with self._lock:
            if len(self._fps_window) < 2:
                return 0.0
            window_s = self._fps_window[-1] - self._fps_window[0]
            if window_s <= 0:
                return 0.0
            return (len(self._fps_window) - 1) / window_s

    # ──────────────────────────────────────────────────────────────────────────
    # METRICS PROCESSING
    # ──────────────────────────────────────────────────────────────────────────

    def _process_frame(self, gray: np.ndarray, now: float) -> None:
        """Compute motion, activity, zones from frame."""
        # Motion (mean absolute difference)
        motion = 0.0
        if self._prev_gray is not None:
            motion = float(
                np.mean(np.abs(gray.astype(np.float32) - self._prev_gray.astype(np.float32)))
            )
        self._prev_gray = gray.copy()
        self._last_motion = motion

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
                self._presence_callback(
                    {
                        "lobe": "streamer",
                        "presence_sync_ok": presence_sync,
                        "activity": self._activity,
                        "motion": motion,
                    }
                )
            except Exception:
                pass

    def _emit_zone(
        self, zone_id: str, state: str, prev: str, delta: float, luma: float, now: float
    ) -> None:
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
                "fps_meas": round(
                    self._measure_actual_fps() or self._frames_processed / elapsed, 2
                ),
                "mean_luma": round(
                    float(np.mean(self._prev_gray)) if self._prev_gray is not None else 0, 2
                ),
                "motion": round(self._last_motion, 3),
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

    def _check_presence(self, now: float) -> tuple[bool, float | None]:
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
