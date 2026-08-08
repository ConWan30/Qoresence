"""
Pluggable OCR providers for the Qoresence Vision Stack.

- VLMOCRProvider: uses a vision-language model (cloud/local VLM).
- PaddleOCRProvider: preferred local engine for gaming HUDs / scoreboards.
- EasyOCRProvider: local deep-learning OCR fallback.
- TesseractOCRProvider: classical local OCR (requires tesseract binary).

Scoreboard path uses ``scoreboard_ocr_engine`` (Paddle first, EasyOCR fallback).
"""

from __future__ import annotations

import logging
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from qoresence.lobes.visual import VLMClient

try:
    from qoresence.vision.local_vlm import LocalVLMClient
except ImportError:
    LocalVLMClient = VLMClient  # type: ignore

log = logging.getLogger(__name__)


def _resize_for_ocr(frame: np.ndarray, max_dim: int = 640) -> np.ndarray:
    h, w = frame.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    return frame


@dataclass
class OCRResult:
    """Structured OCR output."""

    text: str
    confidence: float
    provider: str
    raw_details: dict | None = None


class BaseOCRProvider(ABC):
    """Abstract OCR provider."""

    name: str = "base"

    @abstractmethod
    def read_text(self, frame: np.ndarray) -> OCRResult:
        """Extract text from a BGR frame."""

    def warmup(self) -> None:
        """Optional initialization / model download."""
        return None


class VLMOCRProvider(BaseOCRProvider):
    """
    OCR via a vision-language model.

    Prompts the VLM to return a comma-separated list of visible text.
    Default provider because it understands game UI context and avoids
    classical OCR failures on stylized fonts / low-contrast HUDs.
    """

    name = "vlm"

    def __init__(self, vlm_client):  # VLMClient | LocalVLMClient
        self._client = vlm_client
        self._prompt = (
            "You are an OCR engine. Read only the actual text, numbers, and symbols visible in the image. "
            "Do not describe objects, colors, layout, or people. "
            "Do not include the word 'white' or any color names unless they are literally printed text. "
            "Output a single comma-separated list of text strings. "
            "If no readable text is visible, answer exactly: NO_TEXT."
        )

    def read_text(self, frame: np.ndarray) -> OCRResult:
        frame = _resize_for_ocr(frame, max_dim=640)
        # Short max_tokens keeps OCR responses concise and reduces hallucination
        raw = self._client.analyze_frame_raw(frame, self._prompt, max_tokens=100)
        if raw is None:
            return OCRResult(text="", confidence=0.0, provider=self.name)

        text = raw.strip()
        if text.lower() in {"no_text", "", "none"}:
            return OCRResult(text="", confidence=0.0, provider=self.name)

        # Strip common prose and normalize
        text = re.sub(r"(?i)^text[:\-]?\s*", "", text)
        text = re.sub(r"\n+", ", ", text)
        return OCRResult(
            text=text, confidence=0.85, provider=self.name, raw_details={"raw_response": raw}
        )


class PaddleOCRProvider(BaseOCRProvider):
    """Local PaddleOCR — preferred for stylized game HUD digits."""

    name = "paddle"

    def __init__(self) -> None:
        from qoresence.vision.scoreboard_ocr_engine import PaddleScoreboardEngine

        self._eng = PaddleScoreboardEngine()

    def warmup(self) -> None:
        self._eng.start_warmup()

    def read_text(self, frame: np.ndarray) -> OCRResult:
        self.warmup()
        boxes = self._eng.read_boxes(frame)
        if not boxes:
            return OCRResult(text="", confidence=0.0, provider=self.name)
        parts = [b.text for b in boxes if b.text]
        conf = sum(b.conf for b in boxes) / max(1, len(boxes))
        return OCRResult(
            text=", ".join(parts),
            confidence=conf,
            provider=self.name,
            raw_details={"detections": len(parts)},
        )


class EasyOCRProvider(BaseOCRProvider):
    """
    Local deep-learning OCR via EasyOCR (fallback).

    Auto-downloads English model on first use. Prefer PaddleOCR for scoreboards.
    """

    name = "easyocr"
    _shared_reader: Any | None = None
    _shared_lock = threading.Lock()

    def __init__(self, languages: tuple[str, ...] = ("en",), gpu: bool = False):
        self._languages = languages
        self._gpu = gpu
        self._reader: Any | None = None  # type: ignore

    def warmup(self) -> None:
        with self._shared_lock:
            if EasyOCRProvider._shared_reader is None:
                import easyocr

                log.info("EasyOCR downloading / loading models (first use only)...")
                EasyOCRProvider._shared_reader = easyocr.Reader(
                    list(self._languages), gpu=self._gpu, verbose=False
                )
            self._reader = EasyOCRProvider._shared_reader

    def read_text(self, frame: np.ndarray) -> OCRResult:
        bboxes = self.read_text_with_bboxes(frame)
        if not bboxes:
            return OCRResult(text="", confidence=0.0, provider=self.name)

        parts = [text for (_bbox, text, _conf) in bboxes if text]
        total_conf = sum(conf for (_bbox, _text, conf) in bboxes if _text)
        joined = ", ".join(parts)
        avg_conf = total_conf / len(parts) if parts else 0.0
        return OCRResult(
            text=joined,
            confidence=avg_conf,
            provider=self.name,
            raw_details={"detections": len(parts)},
        )

    def read_text_with_bboxes(
        self, frame: np.ndarray, max_dim: int = 640
    ) -> list[tuple[list[tuple[float, float]], str, float]]:
        """Return per-word OCR results with bounding boxes."""
        self.warmup()
        if self._reader is None:
            return []

        frame = _resize_for_ocr(frame, max_dim=max_dim)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        try:
            # detail=1 returns (bbox, text, confidence) tuples
            results = self._reader.readtext(rgb, detail=1)
            return results
        except Exception as e:
            log.warning(f"EasyOCR failed: {e}")
            return []


class TesseractOCRProvider(BaseOCRProvider):
    """Classical Tesseract OCR (requires pytesseract + tesseract binary)."""

    name = "tesseract"

    def __init__(self, psm: int = 6):
        self._psm = psm

    def warmup(self) -> None:
        try:
            import pytesseract

            _ = pytesseract.get_tesseract_version()
        except Exception as e:
            log.warning(f"Tesseract not available: {e}")

    def read_text(self, frame: np.ndarray) -> OCRResult:
        try:
            import pytesseract

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            text = pytesseract.image_to_string(binary, config=f"--psm {self._psm}").strip()
            return OCRResult(text=text, confidence=0.6 if text else 0.0, provider=self.name)
        except Exception as e:
            log.warning(f"Tesseract OCR failed: {e}")
            return OCRResult(text="", confidence=0.0, provider=self.name)


def create_ocr_provider(
    provider: str, vlm_client: VLMClient | None = None, **kwargs
) -> BaseOCRProvider:
    """Factory for OCR providers."""
    provider = provider.lower()
    if provider == "vlm":
        if vlm_client is None:
            raise ValueError("VLM OCR provider requires a VLMClient")
        return VLMOCRProvider(vlm_client)
    if provider in ("paddle", "paddleocr"):
        return PaddleOCRProvider()
    if provider == "easyocr":
        return EasyOCRProvider(**kwargs)
    if provider == "tesseract":
        return TesseractOCRProvider(**kwargs)
    raise ValueError(f"Unknown OCR provider: {provider}")
