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

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from qoresence.core import GameProfileId
from qoresence.lobes.visual import VLMClient

try:
    from qoresence.vision.local_vlm import LocalVLMClient as _LocalVLMClient

    VLMClientLike = VLMClient | _LocalVLMClient
except Exception:
    VLMClientLike = VLMClient  # type: ignore[misc,assignment]

from .hud_detector import HUDDetector, HUDRegion
from .motion_tracker import MotionEvidence, MotionTracker
from .ocr_providers import BaseOCRProvider, OCRResult, VLMOCRProvider
from .visual_context import GameCategory, GameState, VisualContext, build_vlm_prompt

log = logging.getLogger(__name__)


@dataclass
class VisionEvidence:
    """All evidence extracted from a single frame."""

    timestamp_ns: int
    vlm_game: GameProfileId | None
    vlm_confidence: float
    vlm_response: str
    ocr_text: str
    ocr_confidence: float
    ocr_provider: str
    motion: MotionEvidence | None
    hud_regions: list[HUDRegion]
    visual_context: VisualContext | None = None
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
        vlm_client: VLMClientLike,
        ocr_provider: BaseOCRProvider | None = None,
        enable_motion: bool = False,
        enable_hud: bool = False,
        model_dir: Path | None = None,
        ocr_on_crops: bool = True,
        max_workers: int = 3,
        game_profile: GameProfileId = GameProfileId.NCAA_FOOTBALL_27,
        max_input_dim: int = 640,
    ):
        self._vlm_client = vlm_client

        # Default OCR provider is VLM-as-OCR
        self._ocr_provider = ocr_provider or VLMOCRProvider(vlm_client)

        self._enable_motion = enable_motion
        self._enable_hud = enable_hud
        self._ocr_on_crops = ocr_on_crops
        self._max_workers = max_workers
        self._game_profile = game_profile
        self._max_input_dim = max_input_dim

        self._motion = MotionTracker() if enable_motion else None
        self._hud_detector = HUDDetector(model_dir=model_dir) if enable_hud else None

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="visionstack-"
        )

        # Game-aware JSON prompt: VLM returns structured VisualContext fields
        _football_profiles = {
            GameProfileId.NCAA_FOOTBALL_27,
            GameProfileId.MADDEN_27,
        }
        prompt_category = (
            "football" if game_profile in _football_profiles else "shooter"
        )
        self._game_prompt = build_vlm_prompt(prompt_category)

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

    def analyze(self, frame: np.ndarray) -> VisionEvidence | None:
        """Run the full synchronized stack on one frame."""
        from qoresence.core import clock_ns

        # Clamp input resolution.  The heavy local models (YOLO, OCR) were
        # allocating multi-MB float32 tensors on full-res HDMI frames and
        # exhausting OpenCV's allocator.
        h, w = frame.shape[:2]
        if max(h, w) > self._max_input_dim:
            scale = self._max_input_dim / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        timestamp_ns = clock_ns()

        # VLM game classification (must run, not parallel because it uses the GPU session)
        vlm_raw = None
        visual_context: VisualContext | None = None
        try:
            vlm_raw = self._vlm_client.analyze_frame_raw(
                frame, self._game_prompt, max_tokens=400, game_profile=self._game_profile
            )
            visual_context = self._parse_vlm_context(vlm_raw, frame)
        except Exception as e:
            log.warning(f"VLM game classification failed: {e}")

        vlm_game, vlm_confidence = self._visual_context_to_game_profile(visual_context, vlm_raw)

        # HUD detection in parallel
        hud_regions: list[HUDRegion] = []
        if self._enable_hud and self._hud_detector:
            try:
                hud_regions = self._hud_detector.detect(frame)
            except Exception as e:
                log.warning(f"HUD detection failed: {e}")

        # Motion in parallel with OCR
        motion_future: Any | None = None
        if self._enable_motion and self._motion:
            motion_future = self._executor.submit(self._motion.analyze, frame)

        # OCR on full frame + HUD crops
        ocr_result = self._run_ocr(frame, hud_regions)

        # Collect motion result
        motion: MotionEvidence | None = None
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
            visual_context=visual_context,
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
            crop = frame[region.y1 : region.y2, region.x1 : region.x2]
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
            raw_details={
                "crops": len(crop_texts),
                "regions": [r.label for r in sorted_regions[:2]],
            },
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
                "white",
                "black",
                "red",
                "green",
                "blue",
                "gray",
                "yellow",
                "background",
                "wall",
                "ceiling",
                "floor",
                "screen",
                "tv",
            }:
                continue
            seen.add(lower)
            unique.append(token)

        # Hard cap to avoid runaway VLM lists
        if len(unique) > 100:
            unique = unique[:100]
        return ", ".join(unique)

    @staticmethod
    def _parse_vlm_context(raw: str | None, frame: np.ndarray) -> VisualContext | None:
        """Parse a JSON VLM response into a VisualContext."""
        import hashlib

        if not raw:
            return None

        # Try to find a JSON object in the response
        text = raw.strip()
        # Some VLMs wrap the JSON in markdown fences or explanatory text
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None

        ctx = VisualContext.from_dict(parsed)
        ctx.raw_response = raw

        # Stable frame hash for provenance
        small = cv2.resize(frame, (160, 90))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        ctx.frame_hash = hashlib.sha256(gray.tobytes()).hexdigest()[:16]

        return ctx

    @staticmethod
    def _visual_context_to_game_profile(
        context: VisualContext | None, raw: str | None
    ) -> tuple[GameProfileId | None, float]:
        """Map a VisualContext to a GameProfileId and confidence."""
        if context is not None:
            title = (context.game_title or "").lower()
            state = context.game_state
            category = context.game_category

            # Explicit game title takes priority
            if "ncaa" in title or "college football" in title:
                return GameProfileId.NCAA_FOOTBALL_27, context.confidence
            if "madden" in title or "nfl" in title:
                return GameProfileId.MADDEN_27, context.confidence
            if "call of duty" in title or "cod" in title or "warzone" in title:
                return GameProfileId.CALL_OF_DUTY, context.confidence

            # Fall back to category + game_state
            if state == GameState.GAMEPLAY or state == GameState.PAUSED:
                if category == GameCategory.FOOTBALL:
                    return GameProfileId.NCAA_FOOTBALL_27, context.confidence
                if category == GameCategory.SHOOTER:
                    return GameProfileId.CALL_OF_DUTY, context.confidence

            if state in (
                GameState.MENU,
                GameState.LOBBY,
                GameState.LOADING,
                GameState.RESULTS,
                GameState.CUTSCENE,
            ):
                # Menu is still useful signal but not an active game profile
                return None, context.confidence

        # Fallback to the legacy GAME: / CONFIDENCE: format if JSON parsing failed
        return VisionStack._legacy_parse_vlm_game(raw)

    @staticmethod
    def _legacy_parse_vlm_game(raw: str | None) -> tuple[GameProfileId | None, float]:
        """Parse the legacy two-line VLM game classification response."""
        import re

        if not raw:
            return None, 0.0

        game_match = re.search(r"GAME:\s*([\w\_\-]+)", raw, re.IGNORECASE)
        conf_match = re.search(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", raw, re.IGNORECASE)

        if not game_match:
            return None, 0.0

        label = game_match.group(1).lower().strip()

        aliases = {
            "ncaa_football_27": GameProfileId.NCAA_FOOTBALL_27,
            "ncaa": GameProfileId.NCAA_FOOTBALL_27,
            "madden_27": GameProfileId.MADDEN_27,
            "madden": GameProfileId.MADDEN_27,
            "college_football_27": GameProfileId.NCAA_FOOTBALL_27,
            "college_football": GameProfileId.NCAA_FOOTBALL_27,
            "call_of_duty": GameProfileId.CALL_OF_DUTY,
            "cod": GameProfileId.CALL_OF_DUTY,
        }

        if "|" in label or (label not in aliases and label not in {"menu", "unknown"}):
            return None, 0.0

        confidence = float(conf_match.group(1)) if conf_match else 0.7
        return aliases.get(label), confidence
