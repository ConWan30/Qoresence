"""
Qoresence Vision Stack

Synchronized local computer-vision pipeline for game streams:
- OCR providers (VLM-as-OCR, EasyOCR, Tesseract)
- Motion / camera-velocity tracking (OpenCV + MediaPipe)
- HUD region detection (YOLOv8n via ONNX / OpenVINO)
- VisionStack orchestrator feeding GameAutoDetector
"""

from .ocr_providers import BaseOCRProvider, VLMOCRProvider, EasyOCRProvider, TesseractOCRProvider, create_ocr_provider
from .motion_tracker import MotionTracker, MotionEvidence
from .hud_detector import HUDDetector, HUDRegion
from .vision_stack import VisionStack, VisionEvidence

__all__ = [
    "BaseOCRProvider",
    "VLMOCRProvider",
    "EasyOCRProvider",
    "TesseractOCRProvider",
    "MotionTracker",
    "MotionEvidence",
    "HUDDetector",
    "HUDRegion",
    "VisionStack",
    "VisionEvidence",
]
