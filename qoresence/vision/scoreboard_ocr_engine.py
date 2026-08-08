"""Pluggable scoreboard OCR backends for gaming HUDs.

EasyOCR misreads stylized CFB digits (e.g. 20-0 → 20-20). PaddleOCR is the
recommended local engine for noisy / stylized game UI. EasyOCR remains a
fallback. Optional env:

  QORESENCE_SCOREBOARD_OCR=auto|paddle|easyocr|tesseract
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Protocol

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class OcrBox:
    """One detection in crop-normalized coordinates (0..1)."""

    text: str
    x: float  # center x 0..1 within crop
    y: float  # center y 0..1 within crop
    conf: float
    w: float = 0.0  # box width fraction of crop
    h: float = 0.0  # box height fraction of crop


class ScoreboardOcrEngine(Protocol):
    name: str

    def is_ready(self) -> bool: ...
    def start_warmup(self) -> None: ...
    def read_boxes(self, bgr: np.ndarray) -> list[OcrBox]: ...


def _env_engine() -> str:
    return (os.environ.get("QORESENCE_SCOREBOARD_OCR") or "auto").strip().lower()


class PaddleScoreboardEngine:
    """PaddleOCR — preferred for gaming HUDs (digits, glass, stylized fonts)."""

    name = "paddle"
    _ocr: Any | None = None
    _loading = False
    _failed = False
    _lock = threading.Lock()

    def is_ready(self) -> bool:
        return self._ocr is not None

    def start_warmup(self) -> None:
        if self._ocr is not None or self._failed or self._loading:
            return
        with self._lock:
            if self._ocr is not None or self._failed or self._loading:
                return
            self._loading = True

        def _load() -> None:
            try:
                from paddleocr import PaddleOCR

                log.info("Loading PaddleOCR for scoreboard (background)...")
                # API shifted across paddleocr versions — try modern then legacy kwargs
                last_err: Exception | None = None
                for kwargs in (
                    {"lang": "en", "use_textline_orientation": True},
                    {"lang": "en", "use_angle_cls": True, "show_log": False},
                    {"lang": "en"},
                ):
                    try:
                        PaddleScoreboardEngine._ocr = PaddleOCR(**kwargs)
                        last_err = None
                        break
                    except Exception as e:  # TypeError or runtime
                        last_err = e
                        continue
                if PaddleScoreboardEngine._ocr is None:
                    raise last_err or RuntimeError("PaddleOCR init failed")
                log.info("PaddleOCR scoreboard engine ready")
            except Exception as e:
                PaddleScoreboardEngine._failed = True
                log.warning("PaddleOCR unavailable (%s) — will try EasyOCR / VLM", e)
            finally:
                PaddleScoreboardEngine._loading = False

        threading.Thread(target=_load, name="paddle-ocr-warmup", daemon=True).start()

    def read_boxes(self, bgr: np.ndarray) -> list[OcrBox]:
        self.start_warmup()
        ocr = self._ocr
        if ocr is None:
            return []
        if bgr is None or bgr.size == 0:
            return []
        h, w = bgr.shape[:2]
        if h < 4 or w < 4:
            return []
        # Paddle prefers RGB; keep full res crop (caller already cropped)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        try:
            result = ocr.ocr(rgb, cls=True)
        except TypeError:
            try:
                result = ocr.ocr(rgb)
            except Exception as e:
                log.debug("PaddleOCR ocr failed: %s", e)
                return []
        except Exception as e:
            log.debug("PaddleOCR ocr failed: %s", e)
            return []

        boxes: list[OcrBox] = []
        # result is often [ [ [box, (text, conf)], ... ] ] or similar
        lines = result
        if not lines:
            return []
        if isinstance(lines, list) and lines and isinstance(lines[0], list):
            # unwrap batch dim when present
            if lines and lines[0] and isinstance(lines[0][0], list) and len(lines[0][0]) == 2:
                # already list of [box, (text,conf)]
                pass
            elif lines and isinstance(lines[0], list) and lines[0] and isinstance(lines[0][0], list):
                lines = lines[0]

        for item in lines or []:
            try:
                if not item:
                    continue
                # formats: [box, (text, conf)] or dict-like in newer APIs
                if isinstance(item, dict):
                    text = str(item.get("text") or item.get("rec_text") or "").strip()
                    conf = float(item.get("confidence") or item.get("score") or 0.5)
                    box = item.get("box") or item.get("points") or []
                else:
                    box, rec = item[0], item[1]
                    if isinstance(rec, (list, tuple)):
                        text = str(rec[0]).strip()
                        conf = float(rec[1]) if len(rec) > 1 else 0.5
                    else:
                        text = str(rec).strip()
                        conf = 0.5
                if not text or conf < 0.3:
                    continue
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                if not xs or not ys:
                    continue
                cx = ((min(xs) + max(xs)) / 2.0) / max(1.0, float(w))
                cy = ((min(ys) + max(ys)) / 2.0) / max(1.0, float(h))
                bw = (max(xs) - min(xs)) / max(1.0, float(w))
                bh = (max(ys) - min(ys)) / max(1.0, float(h))
                boxes.append(OcrBox(text=text, x=cx, y=cy, conf=conf, w=bw, h=bh))
            except Exception:
                continue
        return boxes


class EasyOcrScoreboardEngine:
    """EasyOCR fallback — shared background reader."""

    name = "easyocr"
    _reader: Any | None = None
    _loading = False
    _failed = False
    _lock = threading.Lock()

    def is_ready(self) -> bool:
        return self._reader is not None

    def start_warmup(self) -> None:
        if self._reader is not None or self._failed or self._loading:
            return
        with self._lock:
            if self._reader is not None or self._failed or self._loading:
                return
            self._loading = True

        def _load() -> None:
            try:
                import easyocr

                log.info("Loading EasyOCR scoreboard fallback (background)...")
                EasyOcrScoreboardEngine._reader = easyocr.Reader(
                    ["en"], gpu=False, verbose=False
                )
                log.info("EasyOCR scoreboard fallback ready")
            except Exception as e:
                EasyOcrScoreboardEngine._failed = True
                log.warning("EasyOCR scoreboard fallback failed: %s", e)
            finally:
                EasyOcrScoreboardEngine._loading = False

        threading.Thread(target=_load, name="easyocr-scoreboard-warmup", daemon=True).start()

    def read_boxes(self, bgr: np.ndarray) -> list[OcrBox]:
        self.start_warmup()
        reader = self._reader
        if reader is None or bgr is None or bgr.size == 0:
            return []
        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        try:
            results = reader.readtext(rgb, detail=1)
        except Exception as e:
            log.debug("EasyOCR read failed: %s", e)
            return []
        boxes: list[OcrBox] = []
        for bbox, text, conf in results or []:
            try:
                if conf is not None and float(conf) < 0.25:
                    continue
                text = str(text).strip()
                if not text:
                    continue
                xs = [float(p[0]) for p in bbox]
                ys = [float(p[1]) for p in bbox]
                cx = ((min(xs) + max(xs)) / 2.0) / max(1.0, float(w))
                cy = ((min(ys) + max(ys)) / 2.0) / max(1.0, float(h))
                bw = (max(xs) - min(xs)) / max(1.0, float(w))
                bh = (max(ys) - min(ys)) / max(1.0, float(h))
                boxes.append(
                    OcrBox(text=text, x=cx, y=cy, conf=float(conf), w=bw, h=bh)
                )
            except Exception:
                continue
        return boxes


class TesseractScoreboardEngine:
    """Optional Tesseract for clean digit crops (requires system binary)."""

    name = "tesseract"

    def is_ready(self) -> bool:
        try:
            import pytesseract

            _ = pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def start_warmup(self) -> None:
        return None

    def read_boxes(self, bgr: np.ndarray) -> list[OcrBox]:
        if not self.is_ready() or bgr is None or bgr.size == 0:
            return []
        try:
            import pytesseract

            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            data = pytesseract.image_to_data(
                binary, config="--psm 6", output_type=pytesseract.Output.DICT
            )
            h, w = bgr.shape[:2]
            boxes: list[OcrBox] = []
            n = len(data.get("text") or [])
            for i in range(n):
                text = str(data["text"][i] or "").strip()
                if not text:
                    continue
                conf = float(data["conf"][i])
                if conf < 0:
                    conf = 0.4
                else:
                    conf = conf / 100.0
                if conf < 0.3:
                    continue
                x, y, bw, bh = (
                    int(data["left"][i]),
                    int(data["top"][i]),
                    int(data["width"][i]),
                    int(data["height"][i]),
                )
                cx = (x + bw / 2) / max(1, w)
                cy = (y + bh / 2) / max(1, h)
                boxes.append(
                    OcrBox(
                        text=text,
                        x=cx,
                        y=cy,
                        conf=conf,
                        w=bw / max(1, w),
                        h=bh / max(1, h),
                    )
                )
            return boxes
        except Exception as e:
            log.debug("Tesseract scoreboard failed: %s", e)
            return []


_engines: dict[str, ScoreboardOcrEngine] = {}
_active_name: str | None = None


def get_scoreboard_engine(prefer: str | None = None) -> ScoreboardOcrEngine:
    """Resolve engine: auto → paddle if importable else easyocr."""
    global _active_name
    choice = (prefer or _env_engine()).lower()
    if choice == "auto":
        order = ("paddle", "easyocr", "tesseract")
    elif choice in ("paddle", "easyocr", "tesseract"):
        order = (choice, "easyocr", "paddle")
    else:
        order = ("paddle", "easyocr")

    for name in order:
        eng = _engines.get(name)
        if eng is None:
            if name == "paddle":
                eng = PaddleScoreboardEngine()
            elif name == "easyocr":
                eng = EasyOcrScoreboardEngine()
            else:
                eng = TesseractScoreboardEngine()
            _engines[name] = eng
        # Prefer ready engines; otherwise kick warmup on first viable
        if name == "paddle":
            try:
                import paddleocr  # noqa: F401
            except Exception:
                continue
        if name == "easyocr":
            try:
                import easyocr  # noqa: F401
            except Exception:
                continue
        if name == "tesseract" and not eng.is_ready():
            continue
        eng.start_warmup()
        if _active_name != name:
            log.info("Scoreboard OCR engine: %s (request=%s)", name, choice)
            _active_name = name
        return eng

    # Last resort empty easyocr shell
    eng = _engines.get("easyocr") or EasyOcrScoreboardEngine()
    _engines["easyocr"] = eng
    eng.start_warmup()
    return eng
