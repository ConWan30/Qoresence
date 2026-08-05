"""
HUD region detector for the Qoresence Vision Stack.

Auto-downloads YOLOv8n, exports it to ONNX, and runs it with
ONNX Runtime + OpenVINO execution provider when available.

Since COCO-pretrained YOLOv8n does not know "HUD", this class uses it as a
generic region proposal network: it keeps detections of classes likely to
appear in a game scene (tv, person, sports ball for a football) and also
falls back to edge-based region proposals for scoreboard-like rectangles.
In production the model should be fine-tuned on game HUD frames.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False

try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False

log = logging.getLogger(__name__)


@dataclass
class HUDRegion:
    """Detected region of interest in the frame."""
    label: str
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


class HUDDetector:
    """
    Detects likely HUD / scoreboard / gameplay regions.

    - Auto-downloads YOLOv8n (via Ultralytics) on first use.
    - Exports to ONNX if the .onnx file does not exist.
    - Uses ONNX Runtime with OpenVINO execution provider if available,
      otherwise CPU execution provider.
    """

    DEFAULT_CLASSES = {"tv", "person", "sports ball", "clock"}

    def __init__(
        self,
        model_dir: Optional[Path] = None,
        input_size: tuple[int, int] = (384, 640),  # (height, width) as used by YOLO
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        use_openvino: bool = True,
    ):
        self._model_dir = model_dir or Path("models")
        self._model_dir.mkdir(parents=True, exist_ok=True)
        # Store as (height, width); OpenCV needs (width, height)
        self._input_size = input_size
        self._conf_threshold = conf_threshold
        self._iou_threshold = iou_threshold
        self._use_openvino = use_openvino

        self._model_path: Optional[Path] = None
        self._session: Optional[Any] = None

    def warmup(self) -> None:
        """Download and prepare the ONNX model."""
        if self._session is not None:
            return

        if not ONNX_AVAILABLE:
            raise RuntimeError("onnxruntime is not installed")

        # Make openvino.dll discoverable by onnxruntime-openvino
        if self._use_openvino:
            try:
                import openvino
                openvino_dir = Path(openvino.__file__).parent
                libs_dir = openvino_dir / "libs"
                if libs_dir.exists():
                    import os
                    os.environ["PATH"] = str(libs_dir) + os.pathsep + os.environ.get("PATH", "")
            except Exception:
                pass

        self._model_path = self._ensure_onnx_model()

        providers = []
        if self._use_openvino and "OpenVINOExecutionProvider" in ort.get_available_providers():
            providers.append("OpenVINOExecutionProvider")
        providers.append("CPUExecutionProvider")

        log.info(f"HUDDetector using ONNX Runtime providers: {providers}")
        self._session = ort.InferenceSession(str(self._model_path), providers=providers)

    def _ensure_onnx_model(self) -> Path:
        """Return path to yolov8n.onnx, downloading/exporting if necessary."""
        onnx_path = self._model_dir / "yolov8n.onnx"
        if onnx_path.exists():
            return onnx_path

        if not ULTRALYTICS_AVAILABLE:
            raise RuntimeError("ultralytics is not installed; cannot download YOLOv8n")

        log.info("HUDDetector downloading YOLOv8n (first use only)...")
        pt_path = self._model_dir / "yolov8n.pt"
        if not pt_path.exists():
            # Ultralytics will auto-download the .pt file
            YOLO("yolov8n.pt")
            # Move to model_dir if it downloaded elsewhere
            downloaded = Path.home() / ".cache" / "Ultralytics" / "yolov8n.pt"
            if downloaded.exists():
                pt_path = downloaded
            else:
                # Fallback: ultralytics often writes to current dir
                local_pt = Path("yolov8n.pt")
                if local_pt.exists():
                    pt_path = local_pt

        log.info(f"Exporting YOLOv8n to ONNX ({self._input_size})...")
        model = YOLO(str(pt_path))
        model.export(format="onnx", imgsz=self._input_size, half=False, simplify=True)

        # Exported file is in same dir as .pt
        exported = Path(pt_path).with_suffix(".onnx")
        if not exported.exists():
            raise RuntimeError(f"ONNX export failed: {exported} not found")

        # Copy to model_dir
        final_path = onnx_path
        exported.rename(final_path)
        return final_path

    def detect(self, frame: np.ndarray) -> list[HUDRegion]:
        """Detect regions in a BGR frame."""
        self.warmup()
        if self._session is None:
            return []

        # Preprocess. _input_size is (height, width); OpenCV needs (width, height)
        h, w = frame.shape[:2]
        model_h, model_w = self._input_size
        resized = cv2.resize(frame, (model_w, model_h))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        # Normalize to [0,1] then HWC to CHW
        tensor = rgb.astype(np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))
        tensor = np.expand_dims(tensor, axis=0)

        # ONNX Runtime inference
        input_name = self._session.get_inputs()[0].name
        outputs = self._session.run(None, {input_name: tensor})

        # YOLOv8 ONNX export from Ultralytics produces a single output of
        # shape [1, 84, N] where 84 = 4 bbox + 80 COCO classes.
        # This is post-NMS in recent exports? Actually ultralytics default
        # export includes NMS by default since 8.0.196.
        # We handle both cases gracefully.
        return self._parse_yolo_output(outputs[0], w, h)

    def _parse_yolo_output(self, output: np.ndarray, orig_w: int, orig_h: int) -> list[HUDRegion]:
        """Parse YOLOv8n ONNX output into HUDRegion objects."""
        regions: list[HUDRegion] = []

        # YOLOv8 ONNX export from Ultralytics produces [1, 84, num_anchors]
        # where 84 = 4 bbox coords + 80 COCO classes.
        output = output.squeeze()
        if output.ndim == 2:
            if output.shape[0] == 84 and output.shape[1] > 84:
                output = output.T  # [num_anchors, 84]
        else:
            log.warning(f"Unexpected YOLO output shape: {output.shape}")
            return self._propose_hud_regions(orig_h, orig_w)

        if output.shape[-1] < 84:
            return self._propose_hud_regions(orig_h, orig_w)

        # COCO class names
        coco_names = self._coco_names()

        candidates = []
        for row in output:
            x, y, w, h = row[:4]
            class_logits = row[4:84]
            class_id = int(np.argmax(class_logits))
            conf = float(class_logits[class_id])

            if conf < self._conf_threshold:
                continue

            label = coco_names.get(class_id, f"class_{class_id}")
            # Scale to original frame (input_size is (height, width))
            model_h, model_w = self._input_size
            x1 = int((x - w / 2) / model_w * orig_w)
            y1 = int((y - h / 2) / model_h * orig_h)
            x2 = int((x + w / 2) / model_w * orig_w)
            y2 = int((y + h / 2) / model_h * orig_h)
            candidates.append((conf, label, x1, y1, x2, y2))

        # Basic NMS by class overlap
        candidates.sort(reverse=True)
        kept = []
        for conf, label, x1, y1, x2, y2 in candidates:
            box = (x1, y1, x2, y2)
            if all(self._iou(box, kept_box) < self._iou_threshold for kept_box in kept):
                kept.append(box)
                regions.append(HUDRegion(
                    label=label,
                    x1=max(0, x1),
                    y1=max(0, y1),
                    x2=orig_w + x2 if x2 <= 0 else min(orig_w, x2),  # clamp
                    y2=orig_h + y2 if y2 <= 0 else min(orig_h, y2),
                    confidence=conf,
                ))

        # Fallback: if no COCO classes fit, propose edge-based rectangles for HUD zones
        if not regions:
            regions = self._propose_hud_regions(orig_h, orig_w)

        return regions

    def _iou(self, a: tuple[int, ...], b: tuple[int, ...]) -> float:
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def _propose_hud_regions(self, h: int, w: int) -> list[HUDRegion]:
        """Default HUD region proposals when the model has no detections."""
        # Top scoreboard, bottom status, right-side kill feed
        proposals = [
            ("scoreboard", int(w * 0.2), 0, int(w * 0.8), int(h * 0.12)),
            ("bottom_status", int(w * 0.1), int(h * 0.85), int(w * 0.9), h),
            ("right_feed", int(w * 0.7), int(h * 0.1), w, int(h * 0.6)),
        ]
        regions = []
        for label, x1, y1, x2, y2 in proposals:
            regions.append(HUDRegion(label=label, x1=x1, y1=y1, x2=x2, y2=y2, confidence=0.3))
        return regions

    @staticmethod
    def _coco_names() -> dict[int, str]:
        return {
            0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane",
            5: "bus", 6: "train", 7: "truck", 8: "boat", 9: "traffic light",
            10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench",
            14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep", 19: "cow",
            20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe", 24: "backpack",
            25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase", 29: "frisbee",
            30: "skis", 31: "snowboard", 32: "sports ball", 33: "kite", 34: "baseball bat",
            35: "baseball glove", 36: "skateboard", 37: "surfboard", 38: "tennis racket",
            39: "bottle", 40: "wine glass", 41: "cup", 42: "fork", 43: "knife",
            44: "spoon", 45: "bowl", 46: "banana", 47: "apple", 48: "sandwich", 49: "orange",
            50: "broccoli", 51: "carrot", 52: "hot dog", 53: "pizza", 54: "donut",
            55: "cake", 56: "chair", 57: "couch", 58: "potted plant", 59: "bed",
            60: "dining table", 61: "toilet", 62: "tv", 63: "laptop", 64: "mouse",
            65: "remote", 66: "keyboard", 67: "cell phone", 68: "microwave", 69: "oven",
            70: "toaster", 71: "sink", 72: "refrigerator", 73: "book", 74: "clock",
            75: "vase", 76: "scissors", 77: "teddy bear", 78: "hair drier", 79: "toothbrush",
        }
