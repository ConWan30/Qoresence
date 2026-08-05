"""
VisionStack orchestrator for the Qoresence game-detection pipeline.

Synchronizes, in a single pass over one frame:
- VLM game classification
- OCR (VLM-as-OCR, EasyOCR, or Tesseract) on full frame and HUD crops
- Motion / camera-velocity tracking
- HUD region detection (YOLOv8n + ONNX / OpenVINO)

Outputs a VisionEvidence bundle that GameAutoDetector can fuse into
a game detection decision.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from qoresence.core import GameProfileId
from qoresence.lobes.visual import VLMClient

from .hud_detector import HUDDetector, HUDRegion
from .motion_tracker import MotionTracker, MotionEvidence
from .ocr_providers import BaseOCRProvider, OCRResult, VLMOCRProvider

log = logging.getLogger(__name__)


@dataclass
class VisionEvidence:
    """All evidence extracted from a single frame."""
    timestamp_ns: int
    vlm_game: Optional[GameProfileId]
    vlm_confidence: float
    vlm_response: str
    ocr_text: str
    ocr_confidence: float
    ocr_provider: str
    motion: Optional[MotionEvidence]
    hud_regions: list[HUDRegion]
    details: dict = field(default_factory=dict)


class VisionStack:
    """
    One synchronized vision pipeline.

    The stack minimizes redundant work by sharing frame pre-processing:
    - One downscaled copy for the VLM.
    - One full-res / cropped copy for OCR.
    - One scaled gray copy for motion.
    - One resized copy for HUD detection.
    """

    def __init__(
        self,
        vlm_client: VLMClient,
        ocr_provider: Optional[BaseOCRProvider] = None,
        enable_motion: bool = True,
        enable_hud: bool = True,
        model_dir: Optional[Path] = None,
        ocr_on_crops: bool = True,
        max_workers: int = 3,
    ):
        self._vlm_client = vlm_client

        # Default OCR provider is VLM-as-OCR
        self._ocr_provider = ocr_provider or VLMOCRProvider(vlm_client)

        self._enable_motion = enable_motion
        self._enable_hud = enable_hud
        self._ocr_on_crops = ocr_on_crops
        self._max_workers = max_workers

        self._motion = MotionTracker() if enable_motion else None
        self._hud_detector = HUDDetector(model_dir=model_dir) if enable_hud else None

        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="visionstack-")

        # Reusable VLM classification prompt
        self._game_prompt = (
            "Identify the video game shown in this image. "
            "Choose exactly one of these labels: ncaa_football_27 (also college_football_27 or ncaa), "
            "call_of_duty (also cod), menu, unknown.\n\n"
            "Output format (no explanation):\n"
            "GAME: ncaa_football_27\n"
            "CONFIDENCE: 0.95\n\n"
            "Rules:\n"
            "- Pick 'menu' for pause screens, settings, or lobbies.\n"
            "- Pick 'unknown' when the image is black, blurry, or unrecognizable.\n"
            "- Only return the two lines above."
        )

    def warmup(self) -> None:
        """Pre-load / download all models."""
        if self._hud_detector:
            try:
                self._hud_detector.warmup()
            except Exception as e:
                log.warning(f"HUD detector warmup failed: {e}")
        try:
            self._ocr_provider.warmup()
        except Exception as e:
            log.warning(f"OCR provider warmup failed: {e}")

    def stop(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def analyze(self, frame: np.ndarray) -> Optional[VisionEvidence]:
        """Run the full synchronized stack on one frame."""
        from qoresence.core import clock_ns

        timestamp_ns = clock_ns()

        # VLM game classification (must run, not parallel because it uses the GPU session)
        vlm_raw = None
        try:
            vlm_raw = self._vlm_client.analyze_frame_raw(frame, self._game_prompt)
        except Exception as e:
            log.warning(f"VLM game classification failed: {e}")

        vlm_game, vlm_confidence = self._parse_vlm_game(vlm_raw)

        # HUD detection in parallel
        hud_regions: list[HUDRegion] = []
        if self._enable_hud and self._hud_detector:
            try:
                hud_regions = self._hud_detector.detect(frame)
            except Exception as e:
                log.warning(f"HUD detection failed: {e}")

        # Motion in parallel with OCR
        motion_future: Optional[Any] = None
        if self._enable_motion and self._motion:
            motion_future = self._executor.submit(self._motion.analyze, frame)

        # OCR on full frame + HUD crops
        ocr_result = self._run_ocr(frame, hud_regions)

        # Collect motion result
        motion: Optional[MotionEvidence] = None
        if motion_future:
            try:
                motion = motion_future.result(timeout=1.0)
            except TimeoutError:
                log.warning("Motion analysis timed out")

        return VisionEvidence(
            timestamp_ns=timestamp_ns,
            vlm_game=vlm_game,
            vlm_confidence=vlm_confidence,
            vlm_response=vlm_raw or "",
            ocr_text=ocr_result.text,
            ocr_confidence=ocr_result.confidence,
            ocr_provider=ocr_result.provider,
            motion=motion,
            hud_regions=hud_regions,
            details={
                "vlm_raw_response": vlm_raw,
                "hud_region_count": len(hud_regions),
            },
        )

    def _run_ocr(self, frame: np.ndarray, hud_regions: list[HUDRegion]) -> OCRResult:
        """Run OCR on the most relevant HUD crop(s). Full frame only as fallback."""
        if not hud_regions:
            # No HUD regions: run on full frame
            return self._ocr_provider.read_text(frame)

        # Sort by area and confidence to pick the best screen / content crops
        sorted_regions = sorted(
            hud_regions,
            key=lambda r: (r.y2 - r.y1) * (r.x2 - r.x1) * r.confidence,
            reverse=True,
        )

        crop_texts: list[str] = []
        crop_confs: list[float] = []

        for region in sorted_regions[:2]:  # top 2 largest / most confident regions
            crop = frame[region.y1:region.y2, region.x1:region.x2]
            if crop.size == 0:
                continue
            try:
                crop_result = self._ocr_provider.read_text(crop)
                if crop_result.text:
                    crop_texts.append(crop_result.text)
                    crop_confs.append(crop_result.confidence)
            except Exception as e:
                log.debug(f"OCR crop failed for {region.label}: {e}")

        if not crop_texts:
            # Crops yielded no text; fall back to full frame
            return self._ocr_provider.read_text(frame)

        # Clean the merged text: collapse duplicates, limit length
        merged = self._deduplicate_text(", ".join(t for t in crop_texts if t))
        avg_conf = float(sum(crop_confs) / len(crop_confs)) if crop_confs else 0.0
        return OCRResult(
            text=merged,
            confidence=avg_conf,
            provider=self._ocr_provider.name,
            raw_details={"crops": len(crop_texts), "regions": [r.label for r in sorted_regions[:2]]},
        )

    @staticmethod
    def _deduplicate_text(text: str) -> str:
        """Remove repeated tokens and excessive noise from merged OCR."""
        tokens = [t.strip() for t in text.split(",") if t.strip()]
        seen: set[str] = set()
        unique: list[str] = []
        for token in tokens:
            lower = token.lower()
            if lower in seen:
                continue
            # Filter noisy / overly generic tokens that VLM OCR often hallucinates
            if lower in {
                "white", "black", "red", "green", "blue", "gray", "yellow",
                "background", "wall", "ceiling", "floor", "screen", "tv",
            }:
                continue
            seen.add(lower)
            unique.append(token)

        # Hard cap to avoid runaway VLM lists
        if len(unique) > 100:
            unique = unique[:100]
        return ", ".join(unique)

    @staticmethod
    def _parse_vlm_game(raw: Optional[str]) -> tuple[Optional[GameProfileId], float]:
        """Parse the VLM game classification response."""
        import re

        if not raw:
            return None, 0.0

        game_match = re.search(r"GAME:\s*([\w\_\-]+)", raw, re.IGNORECASE)
        conf_match = re.search(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", raw, re.IGNORECASE)

        if not game_match:
            return None, 0.0

        label = game_match.group(1).lower().strip()

        # Accept common aliases the VLM may use instead of the canonical profile id
        aliases = {
            "ncaa_football_27": GameProfileId.NCAA_FOOTBALL_27,
            "ncaa": GameProfileId.NCAA_FOOTBALL_27,
            "college_football_27": GameProfileId.NCAA_FOOTBALL_27,
            "college_football": GameProfileId.NCAA_FOOTBALL_27,
            "call_of_duty": GameProfileId.CALL_OF_DUTY,
            "cod": GameProfileId.CALL_OF_DUTY,
        }

        if "|" in label or (label not in aliases and label not in {"menu", "unknown"}):
            return None, 0.0

        confidence = float(conf_match.group(1)) if conf_match else 0.7

        mapping = aliases

        return mapping.get(label), confidence
