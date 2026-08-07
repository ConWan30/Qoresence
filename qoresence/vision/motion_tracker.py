"""
Motion / camera-velocity tracker for the Qoresence Vision Stack.

- OpenCV Farneback dense optical flow for global camera velocity.
- OpenCV KLT sparse tracking for foreground / object motion.
- MediaPipe ObjectDetector for ROI masking (optional).

The MediaPipe C++ MotionAnalysis graph is not exposed in the modern
mediapipe Python package (0.10.x), so this module uses the same underlying
OpenCV KLT/Farneback algorithms that MediaPipe uses internally.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

log = logging.getLogger(__name__)

MEDIAPIPE_AVAILABLE = False
try:
    import mediapipe as mp  # noqa: F401
    from mediapipe.tasks.python.core.base_options import BaseOptions
    from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode

    # The wheel on this platform does not expose mediapipe.tasks.vision directly;
    # the real modules live under mediapipe.tasks.python.{vision,core}.
    from mediapipe.tasks.python.vision.object_detector import ObjectDetector, ObjectDetectorOptions

    MEDIAPIPE_AVAILABLE = True
except ImportError as _e:
    log.debug(f"MediaPipe Tasks Python API not available: {_e}")


@dataclass
class MotionEvidence:
    """Motion analysis result for one frame."""

    camera_velocity: float  # global flow magnitude (pixels/frame)
    object_velocity: float  # median flow in detected ROIs
    flow_confidence: float  # 0.0-1.0, based on feature count and spread
    motion_class_hint: str  # "low" | "medium" | "high"
    raw_details: dict


class MotionTracker:
    """
    Tracks camera and object motion from a sequence of frames.

    Uses OpenCV optical flow. MediaPipe ObjectDetector (if available)
    provides masks to separate foreground object motion from camera panning.
    """

    def __init__(
        self,
        history: int = 5,
        flow_scale: float = 0.5,
        use_mediapipe_mask: bool = True,
        max_mediapipe_detections: int = 5,
    ):
        self._history = history
        self._flow_scale = flow_scale
        self._use_mediapipe_mask = use_mediapipe_mask and MEDIAPIPE_AVAILABLE

        self._prev_gray: np.ndarray | None = None
        self._prev_frame: np.ndarray | None = None

        # Motion history for smoothing
        self._camera_vel: deque[float] = deque(maxlen=history)
        self._object_vel: deque[float] = deque(maxlen=history)

        # MediaPipe object detector lazy init
        self._object_detector: Any | None = None  # type: ignore
        self._max_detections = max_mediapipe_detections

    def _ensure_detector(self) -> None:
        if self._object_detector is not None or not self._use_mediapipe_mask:
            return
        try:
            model_path = self._ensure_mediapipe_model()
            options = ObjectDetectorOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                running_mode=VisionTaskRunningMode.IMAGE,
                max_results=self._max_detections,
                score_threshold=0.3,
            )
            self._object_detector = ObjectDetector.create_from_options(options)
        except Exception as e:
            log.warning(f"MediaPipe object detector not available: {e}")
            self._use_mediapipe_mask = False

    @staticmethod
    def _ensure_mediapipe_model() -> str:
        """Download EfficientDet-Lite0 tflite model if not present."""
        import urllib.request
        from pathlib import Path

        model_dir = Path("models")
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / "efficientdet_lite0.tflite"
        if model_path.exists():
            return str(model_path)

        url = "https://storage.googleapis.com/mediapipe-tasks/object_detector/efficientdet_lite0_uint8.tflite"
        log.info(f"Downloading MediaPipe object-detection model to {model_path}...")
        urllib.request.urlretrieve(url, model_path)
        return str(model_path)

    def _get_roi_mask(self, frame: np.ndarray) -> np.ndarray | None:
        """Return a binary mask of likely foreground objects (player, reticle, etc)."""
        if not self._use_mediapipe_mask:
            return None

        self._ensure_detector()
        if self._object_detector is None:
            return None

        try:
            import mediapipe as mp

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            results = self._object_detector.detect(mp_image)

            h, w = frame.shape[:2]
            mask = np.zeros((h, w), dtype=np.uint8)
            for det in results.detections:
                bbox = det.bounding_box
                x, y = int(bbox.origin_x), int(bbox.origin_y)
                bw, bh = int(bbox.width), int(bbox.height)
                cv2.rectangle(mask, (x, y), (x + bw, y + bh), 255, -1)
            return mask
        except Exception as e:
            log.debug(f"MediaPipe ROI mask failed: {e}")
            return None

    def analyze(self, frame: np.ndarray) -> MotionEvidence:
        """Analyze motion relative to the previous frame."""
        small = cv2.resize(frame, None, fx=self._flow_scale, fy=self._flow_scale)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        if self._prev_gray is None:
            self._prev_gray = gray
            self._prev_frame = small
            return MotionEvidence(
                camera_velocity=0.0,
                object_velocity=0.0,
                flow_confidence=0.0,
                motion_class_hint="low",
                raw_details={"first_frame": True},
            )

        # Dense optical flow (Farneback)
        flow = cv2.calcOpticalFlowFarneback(
            self._prev_gray,
            gray,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )

        # Global camera velocity = robust mean magnitude
        mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        # Clip extreme outliers
        mag = np.clip(mag, 0, np.percentile(mag, 98) if mag.any() else 1.0)
        camera_velocity = float(np.mean(mag)) if mag.size else 0.0

        # ROI / foreground object velocity
        mask = self._get_roi_mask(self._prev_frame) if self._use_mediapipe_mask else None
        if mask is not None:
            mask = cv2.resize(mask, (gray.shape[1], gray.shape[0]))
            masked_mag = mag[mask > 0]
            object_velocity = float(np.median(masked_mag)) if masked_mag.size else camera_velocity
        else:
            # Use sparse KLT on good features to separate local motion
            object_velocity = self._sparse_object_velocity(self._prev_gray, gray)

        # Smoothing
        self._camera_vel.append(camera_velocity)
        self._object_vel.append(object_velocity)
        camera_smooth = float(np.median(self._camera_vel)) if self._camera_vel else 0.0
        object_smooth = float(np.median(self._object_vel)) if self._object_vel else 0.0

        # Confidence based on flow richness
        flow_confidence = min(1.0, mag.size / (small.shape[0] * small.shape[1] + 1e-6))

        # Classify motion level
        if camera_smooth < 2.0:
            motion_class = "low"
        elif camera_smooth < 8.0:
            motion_class = "medium"
        else:
            motion_class = "high"

        self._prev_gray = gray
        self._prev_frame = small

        return MotionEvidence(
            camera_velocity=camera_smooth,
            object_velocity=object_smooth,
            flow_confidence=flow_confidence,
            motion_class_hint=motion_class,
            raw_details={
                "camera_velocity_raw": camera_velocity,
                "object_velocity_raw": object_velocity,
                "roi_mask_used": mask is not None,
            },
        )

    def _sparse_object_velocity(self, prev_gray: np.ndarray, gray: np.ndarray) -> float:
        """Use KLT to estimate foreground / local object velocity."""
        p0 = cv2.goodFeaturesToTrack(
            prev_gray, maxCount=100, qualityLevel=0.3, minDistance=7, blockSize=7
        )
        if p0 is None:
            return 0.0

        p1, st, err = cv2.calcOpticalFlowPyrLK(
            prev_gray, gray, p0, None, winSize=(15, 15), maxLevel=2
        )
        if p1 is None or st is None:
            return 0.0

        good_prev = p0[st == 1]
        good_new = p1[st == 1]
        if len(good_prev) == 0:
            return 0.0

        # Displacement magnitudes; high displacement likely object, low likely camera
        diffs = good_new - good_prev
        mags = np.linalg.norm(diffs, axis=1)
        # Use 75th percentile as object motion estimate
        return float(np.percentile(mags, 75))
