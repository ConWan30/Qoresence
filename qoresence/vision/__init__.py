"""
Qoresence Vision Stack

Synchronized local computer-vision pipeline for game streams:
- OCR providers (VLM-as-OCR, EasyOCR, Tesseract)
- Motion / camera-velocity tracking (OpenCV + MediaPipe)
- HUD region detection (YOLOv8n via ONNX / OpenVINO)
- VisionStack orchestrator feeding GameAutoDetector
- Local distilled VLM (offline <100ms)
"""

from .hud_detector import HUDDetector, HUDRegion
from .local_vlm import LocalVLMClient, create_local_vlm_client
from .motion_tracker import MotionEvidence, MotionTracker
from .ocr_providers import (
    BaseOCRProvider,
    EasyOCRProvider,
    TesseractOCRProvider,
    VLMOCRProvider,
    create_ocr_provider,
)
from .vision_stack import VisionEvidence, VisionStack
from .title_presence import PLANE as TITLE_PRESENCE_PLANE
from .visual_context import GameCategory, GameState, VisualContext, build_vlm_prompt

__all__ = [
    "BaseOCRProvider",
    "VLMOCRProvider",
    "EasyOCRProvider",
    "TesseractOCRProvider",
    "create_ocr_provider",
    "MotionTracker",
    "MotionEvidence",
    "HUDDetector",
    "HUDRegion",
    "VisualContext",
    "GameState",
    "GameCategory",
    "build_vlm_prompt",
    "VisionStack",
    "VisionEvidence",
    "LocalVLMClient",
    "create_local_vlm_client",
    "TITLE_PRESENCE_PLANE",
]
