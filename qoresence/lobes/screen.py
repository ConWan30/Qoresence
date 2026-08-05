"""
Qoresence Screen Lobe — Phase 7

Screen capture (mss/DXGI), CV coupling score, HUD OCR for NCAA/CoD.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2
import mss
import numpy as np

from qoresence.core import (
    RetinaEventBus,
    SourceLobe,
    EventType,
    clock_ns,
    ScreenConfig,
)

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ScreenRegion:
    """Screen region for capture/OCR."""
    left: int
    top: int
    width: int
    height: int
    name: str = ""

    def to_mss(self) -> dict:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


@dataclass
class CouplingSample:
    """Single sample for coupling analysis."""
    controller_ts_ns: int
    screen_ts_ns: int
    controller_feature: np.ndarray  # e.g., trigger value, stick position
    screen_feature: np.ndarray      # e.g., motion in region, color change


# ──────────────────────────────────────────────────────────────────────────────
# HUD REGIONS (normalized coordinates)
# ──────────────────────────────────────────────────────────────────────────────

NCAA_HUD_REGIONS = {
    "scoreboard": (0.15, 0.02, 0.7, 0.08),
    "down_distance": (0.05, 0.10, 0.25, 0.06),
    "possession": (0.75, 0.02, 0.2, 0.04),
    "play_clock": (0.45, 0.08, 0.1, 0.04),
    "game_clock": (0.85, 0.02, 0.1, 0.04),
    "quarter": (0.05, 0.02, 0.1, 0.04),
    "yard_line": (0.3, 0.90, 0.4, 0.06),
}

COD_HUD_REGIONS = {
    "kill_feed": (0.7, 0.15, 0.25, 0.6),
    "score": (0.05, 0.02, 0.2, 0.05),
    "health": (0.05, 0.90, 0.2, 0.05),
    "ammo": (0.75, 0.90, 0.2, 0.05),
    "mini_map": (0.75, 0.02, 0.2, 0.15),
    "streak": (0.35, 0.02, 0.3, 0.05),
}


# ──────────────────────────────────────────────────────────────────────────────
# SCREEN RUNTIME
# ──────────────────────────────────────────────────────────────────────────────

class ScreenRuntime:
    """
    Screen capture and analysis lobe.

    - Captures screen via mss (cross-platform) or DXGI (Windows, higher perf)
    - Computes CV coupling score between controller input and screen response
    - OCR on HUD regions for NCAA/CoD
    - Emits coupling_score, cv_motion, ocr_hud events
    """

    def __init__(
        self,
        config: ScreenConfig,
        bus: RetinaEventBus,
        session_head_ns: int,
        controller_feature_provider: Optional[Callable[[], Optional[np.ndarray]]] = None,
    ):
        self.config = config
        self.bus = bus
        self.session_head_ns = session_head_ns

        # Optional controller feature provider for coupling
        self._controller_provider = controller_feature_provider

        # Capture backend
        self._use_dxgi = config.capture_method == "dxgi"
        self._sct: Optional[mss.mss] = None
        self._monitor_idx = config.monitor_index

        # HUD regions
        self._hud_regions = self._get_hud_regions()

        # Coupling analysis (using existing config fields)
        self._coupling_buffer = deque(maxlen=300)  # Fixed size
        self._coupling_window_s = 2.0

        # Frame differencing for motion
        self._prev_frame: Optional[np.ndarray] = None

        # State
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frames_captured = 0
        self._start_time = 0.0

        # Motion threshold (configurable for testing)
        self._motion_threshold = 0.01

        # OCR (optional)
        self._tesseract_available = False
        try:
            import pytesseract
            self._tesseract_available = True
        except ImportError:
            pass

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start capture thread."""
        if self._running:
            log.warning("ScreenRuntime already running")
            return True

        try:
            if self._use_dxgi:
                # Try dxcam for DXGI (Windows only)
                try:
                    import dxcam
                    self._camera = dxcam.create(output_idx=self._monitor_idx)
                    self._camera.start(target_fps=self.config.fps_target)
                    log.info(f"DXGI capture started on monitor {self._monitor_idx}")
                except ImportError:
                    log.warning("dxcam not available, falling back to mss")
                    self._use_dxgi = False
                    self._sct = mss.mss()
            else:
                self._sct = mss.mss()
                log.info(f"MSS capture started on monitor {self._monitor_idx}")
        except Exception as e:
            log.error(f"Failed to start screen capture: {e}")
            return False

        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._run_loop, name="qoresence-screen", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop capture thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._use_dxgi and hasattr(self, '_camera'):
            try:
                self._camera.stop()
            except Exception:
                pass
        if self._sct:
            try:
                self._sct.close()
            except Exception:
                pass
        log.info("Screen lobe stopped")

    def is_running(self) -> bool:
        return self._running

    def set_controller_provider(self, provider: Callable[[], Optional[np.ndarray]]) -> None:
        """Set controller feature provider for coupling analysis."""
        self._controller_provider = provider

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN LOOP
    # ──────────────────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Main capture and analysis loop."""
        period = 1.0 / max(self.config.fps_target, 1.0)

        # Emit session_start
        self._emit_session_start()

        while self._running:
            loop_start = time.time()

            # Capture frame
            frame = self._capture_frame()
            if frame is not None:
                self._frames_captured += 1
                self._process_frame(frame)

            # Pace
            elapsed = time.time() - loop_start
            sleep_time = period - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Session end
        self._emit_session_end()

    def _capture_frame(self) -> Optional[np.ndarray]:
        """Capture single frame from screen."""
        try:
            if self._use_dxgi and hasattr(self, '_camera'):
                frame = self._camera.get_latest_frame()
                if frame is not None:
                    # dxcam returns RGB, convert to BGR for OpenCV
                    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            elif self._sct:
                monitor = self._sct.monitors[self._monitor_idx + 1]  # +1 because monitors[0] is all
                screenshot = self._sct.grab(monitor)
                frame = np.array(screenshot)
                # mss returns BGRA, convert to BGR
                if frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                return frame
        except Exception as e:
            log.warning(f"Capture error: {e}")
        return None

    def _process_frame(self, frame: np.ndarray) -> None:
        """Process captured frame."""
        now_ns = clock_ns()

        # 1. Motion detection (frame differencing)
        motion_score = self._detect_motion(frame)

        # 2. HUD OCR
        ocr_results = self._ocr_hud_regions(frame)

        # 3. Coupling analysis (if controller provider available)
        coupling_score = self._analyze_coupling(frame, now_ns)

        # Emit events
        if motion_score > self._motion_threshold:  # Threshold
            self._emit_cv_motion(motion_score, now_ns)

        if coupling_score is not None:
            self._emit_coupling_score(coupling_score, now_ns)

        if ocr_results:
            self._emit_ocr_hud(ocr_results, now_ns)

        self._prev_frame = frame.copy()

    # ──────────────────────────────────────────────────────────────────────────
    # MOTION DETECTION
    # ──────────────────────────────────────────────────────────────────────────

    def _detect_motion(self, frame: np.ndarray) -> float:
        """Detect motion via frame differencing."""
        if self._prev_frame is None:
            return 0.0

        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        prev_gray = cv2.cvtColor(self._prev_frame, cv2.COLOR_BGR2GRAY)

        # Absolute difference
        diff = cv2.absdiff(gray, prev_gray)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)

        # Motion ratio
        motion_pixels = np.count_nonzero(thresh)
        total_pixels = thresh.size
        return motion_pixels / total_pixels

    # ──────────────────────────────────────────────────────────────────────────
    # HUD OCR
    # ──────────────────────────────────────────────────────────────────────────

    def _get_hud_regions(self) -> dict[str, tuple]:
        """Get HUD regions for current game profile."""
        # This would be set based on active game profile
        # For now, return NCAA regions as default
        return NCAA_HUD_REGIONS

    def _ocr_hud_regions(self, frame: np.ndarray) -> dict[str, str]:
        """OCR on HUD regions."""
        results = {}
        h, w = frame.shape[:2]

        for name, (x_frac, y_frac, w_frac, h_frac) in self._hud_regions.items():
            x = int(x_frac * w)
            y = int(y_frac * h)
            rw = int(w_frac * w)
            rh = int(h_frac * h)

            roi = frame[y:y+rh, x:x+rw]
            if roi.size == 0:
                continue

            # Preprocess for OCR
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

            if self._tesseract_available:
                try:
                    import pytesseract
                    text = pytesseract.image_to_string(thresh, config='--psm 7').strip()
                    if text:
                        results[name] = text
                except Exception:
                    pass
            else:
                # Simple template matching fallback
                text = self._simple_ocr(thresh, name)
                if text:
                    results[name] = text

        return results

    def _simple_ocr(self, thresh: np.ndarray, region_name: str) -> Optional[str]:
        """Simple template-based OCR fallback."""
        # Placeholder - real impl would use template matching
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # COUPLING ANALYSIS
    # ──────────────────────────────────────────────────────────────────────────

    def _analyze_coupling(self, frame: np.ndarray, now_ns: int) -> Optional[float]:
        """Analyze controller-screen coupling."""
        if self._controller_provider is None:
            return None

        controller_features = self._controller_provider()
        if controller_features is None:
            return None

        # Extract screen features (motion in key regions)
        screen_features = self._extract_screen_features(frame)
        if screen_features is None:
            return None

        # Add to buffer
        self._coupling_buffer.append(CouplingSample(
            controller_ts_ns=now_ns,  # Approximate
            screen_ts_ns=now_ns,
            controller_feature=controller_features,
            screen_feature=screen_features,
        ))

        # Need enough samples
        if len(self._coupling_buffer) < 10:
            return None

        # Compute cross-correlation at different lags
        controller_seq = np.array([s.controller_feature for s in self._coupling_buffer])
        screen_seq = np.array([s.screen_feature for s in self._coupling_buffer])

        # Flatten if multi-dimensional
        if controller_seq.ndim > 1:
            controller_seq = controller_seq.reshape(len(controller_seq), -1)
        if screen_seq.ndim > 1:
            screen_seq = screen_seq.reshape(len(screen_seq), -1)

        # Use first dimension for correlation
        ctrl_1d = controller_seq[:, 0] if controller_seq.shape[1] > 0 else np.zeros(len(controller_seq))
        scr_1d = screen_seq[:, 0] if screen_seq.shape[1] > 0 else np.zeros(len(screen_seq))

        # Cross-correlation
        max_lag = min(20, len(ctrl_1d) // 2)
        best_corr = 0.0
        best_lag = 0

        for lag in range(-max_lag, max_lag + 1):
            if lag < 0:
                c = ctrl_1d[-lag:]
                s = scr_1d[:lag]
            elif lag > 0:
                c = ctrl_1d[:-lag]
                s = scr_1d[lag:]
            else:
                c = ctrl_1d
                s = scr_1d

            if len(c) > 5 and len(s) > 5:
                corr = np.corrcoef(c, s)[0, 1]
                if not np.isnan(corr) and abs(corr) > abs(best_corr):
                    best_corr = corr
                    best_lag = lag

        # Store best lag for reporting
        self._best_lag = best_lag
        self._best_corr = best_corr

        # Negative control: shuffle controller sequence
        shuffled = np.random.permutation(ctrl_1d)
        neg_corr = np.corrcoef(shuffled, scr_1d)[0, 1]
        self._negative_control = neg_corr if not np.isnan(neg_corr) else 0.0

        return float(best_corr)

    def _extract_screen_features(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Extract features from screen for coupling."""
        # Simple: mean brightness change in center region
        h, w = frame.shape[:2]
        center = frame[h//3:2*h//3, w//3:2*w//3]
        if center.size == 0:
            return None

        gray = cv2.cvtColor(center, cv2.COLOR_BGR2GRAY)
        mean_val = np.mean(gray) / 255.0
        return np.array([mean_val])

    # ──────────────────────────────────────────────────────────────────────────
    # EVENT EMISSION
    # ──────────────────────────────────────────────────────────────────────────

    def _emit_session_start(self) -> None:
        self.bus.emit_raw(
            source_lobe=SourceLobe.SCREEN,
            event_type="session_start",
            payload={
                "capture_fps": self.config.fps_target,
                "capture_method": self.config.capture_method,
                "monitor_index": self._monitor_idx,
                "use_dxgi": self._use_dxgi,
                "cv_motion_enabled": self.config.cv_motion_enabled,
                "ocr_enabled": self.config.ocr_enabled,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    def _emit_cv_motion(self, motion: float, now_ns: int) -> None:
        self.bus.emit_raw(
            source_lobe=SourceLobe.SCREEN,
            event_type="cv_motion",
            payload={"motion": round(motion, 4)},
            clock_ns_override=now_ns,
            session_head_ns=self.session_head_ns,
        )

    def _emit_coupling_score(self, coupling: float, now_ns: int) -> None:
        self.bus.emit_raw(
            source_lobe=SourceLobe.SCREEN,
            event_type="coupling_score",
            payload={
                "coupling_score": round(coupling, 4),
                "negative_control": round(self._negative_control, 4),
                "best_lag_ms": round(self._best_lag * (1000.0 / self.config.fps_target), 1),
            },
            clock_ns_override=now_ns,
            session_head_ns=self.session_head_ns,
        )

    def _emit_ocr_hud(self, ocr_results: dict[str, str], now_ns: int) -> None:
        for region, text in ocr_results.items():
            self.bus.emit_raw(
                source_lobe=SourceLobe.SCREEN,
                event_type="ocr_hud",
                payload={"region": region, "text": text},
                clock_ns_override=now_ns,
                session_head_ns=self.session_head_ns,
            )

    def _emit_session_end(self) -> None:
        elapsed = max(time.time() - self._start_time, 1e-6)
        self.bus.emit_raw(
            source_lobe=SourceLobe.SCREEN,
            event_type="session_end",
            payload={
                "frames_captured": self._frames_captured,
                "elapsed_s": round(elapsed, 2),
                "avg_fps": round(self._frames_captured / elapsed, 1),
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: List monitors
# ──────────────────────────────────────────────────────────────────────────────

def list_monitors() -> list[dict]:
    """List available monitors for capture."""
    with mss.mss() as sct:
        monitors = []
        for i, mon in enumerate(sct.monitors[1:], 1):  # Skip index 0 (all monitors)
            monitors.append({
                "index": i - 1,
                "left": mon["left"],
                "top": mon["top"],
                "width": mon["width"],
                "height": mon["height"],
            })
        return monitors