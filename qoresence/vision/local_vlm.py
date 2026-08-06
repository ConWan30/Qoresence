"""Local distilled VLM stub — offline <100ms brain.

Tries ONNX model at models/qoresence-vlm-distilled.onnx; falls back to
lightweight heuristic that still returns a valid VisualContext.
Interface mirrors VLMClient.analyze_frame so swapping is trivial.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from qoresence.vision.visual_context import VisualContext, GameCategory, GameState

log = logging.getLogger(__name__)
DEFAULT_ONNX = Path("models/qoresence-vlm-distilled.onnx")


class LocalVLMClient:
    def __init__(self, model_path: str | Path | None = None, fallback: str = "heuristic"):
        self.model_path = Path(model_path) if model_path else DEFAULT_ONNX
        self.fallback = fallback
        self._onnx_sess = None
        self._available = False
        self._mode = "heuristic"
        self._stats = {"calls": 0, "avg_ms": 0.0}
        self._try_load()

    def _try_load(self) -> None:
        if self.model_path.exists():
            try:
                import onnxruntime as ort  # type: ignore
                self._onnx_sess = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
                self._available = True
                self._mode = "onnx"
                log.info(f"LocalVLM ONNX loaded: {self.model_path}")
                return
            except Exception as e:
                log.warning(f"LocalVLM ONNX load failed ({e}), using heuristic")
        self._available = False
        self._mode = "heuristic"

    def is_available(self) -> bool:
        return self._onnx_sess is not None

    def warmup(self) -> None:
        if self._onnx_sess is None:
            return
        try:
            dummy = np.zeros((1, 3, 224, 224), dtype=np.float32)
            self._onnx_sess.run(None, {self._onnx_sess.get_inputs()[0].name: dummy})
        except Exception as e:
            log.debug(f"LocalVLM warmup failed: {e}")

    def get_stats(self) -> dict:
        return {"mode": self._mode, "available": self.is_available(), **self._stats}

    def analyze_frame(self, frame: np.ndarray, prompt: str = "") -> Optional[VisualContext]:
        t0 = time.perf_counter()
        ctx: Optional[VisualContext] = None
        if self._onnx_sess is not None:
            ctx = self._onnx_infer(frame)
        if ctx is None:
            ctx = self._heuristic(frame)
        ms = (time.perf_counter() - t0) * 1000
        n = self._stats["calls"]
        self._stats["avg_ms"] = (self._stats["avg_ms"] * n + ms) / (n + 1)
        self._stats["calls"] += 1
        if ctx:
            ctx.latency_ms = ms
            ctx.model = f"local:{self._mode}"
        if ms > 150:
            log.debug(f"LocalVLM slow: {ms:.1f}ms")
        return ctx

    def analyze_frame_raw(self, frame: np.ndarray, prompt: str, timeout: float = 10, max_tokens: int = 300) -> Optional[str]:
        ctx = self.analyze_frame(frame, prompt)
        if ctx is None:
            return None
        # emit JSON-ish that vision_stack can parse
        import json
        return json.dumps(ctx.to_dict())

    def _onnx_infer(self, frame: np.ndarray) -> Optional[VisualContext]:
        try:
            inp = self._onnx_sess.get_inputs()[0]
            h, w = frame.shape[:2]
            img = cv2.resize(frame, (224, 224))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            img = np.transpose(img, (2, 0, 1))[None]
            out = self._onnx_sess.run(None, {inp.name: img})
            # expect logits [football, shooter, menu, unknown]
            logits = np.array(out[0]).flatten()
            idx = int(np.argmax(logits))
            conf = float(1 / (1 + np.exp(-float(np.max(logits)))))
            cats = [GameCategory.FOOTBALL, GameCategory.SHOOTER, GameCategory.UNKNOWN, GameCategory.UNKNOWN]
            states = [GameState.GAMEPLAY, GameState.GAMEPLAY, GameState.MENU, GameState.UNKNOWN]
            ctx = VisualContext(game_state=states[idx], game_category=cats[idx], confidence=conf)
            # leave scores zero - caller fills via outcome
            return ctx
        except Exception as e:
            log.debug(f"ONNX infer failed: {e}")
            return None

    def _heuristic(self, frame: np.ndarray) -> VisualContext:
        # fast heuristic: luma + edge density + green-field ratio
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (160, 90))
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        # green field ~ hue 35-85
        green = cv2.inRange(hsv, np.array([35, 40, 40]), np.array([85, 255, 255]))
        green_ratio = float((green > 0).mean())
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 180)
        edge_density = float((edges > 0).mean())
        mean_luma = float(gray.mean())
        has_scoreboard = mean_luma > 30 and edge_density > 0.02
        if green_ratio > 0.06 and has_scoreboard:
            return VisualContext(game_state=GameState.GAMEPLAY, game_category=GameCategory.FOOTBALL, confidence=0.72, frame_quality="ok")
        if edge_density > 0.06 and green_ratio < 0.08:
            return VisualContext(game_state=GameState.GAMEPLAY, game_category=GameCategory.SHOOTER, confidence=0.62, frame_quality="ok")
        if mean_luma < 20:
            return VisualContext(game_state=GameState.MENU, game_category=GameCategory.UNKNOWN, confidence=0.45, frame_quality="dark")
        return VisualContext(game_state=GameState.UNKNOWN, game_category=GameCategory.UNKNOWN, confidence=0.35, frame_quality="ok")


    def cross_modal_check(self, frame: np.ndarray, other_modalities: dict) -> None:  # type: ignore[override]
        """Local brain has no cloud VLM — return inconclusive."""
        # Keep interface compatible with VLMClient so VisualRuntime/VisionStack can swap.
        return None

def create_local_vlm_client(model_path: str | Path | None = None) -> LocalVLMClient:
    return LocalVLMClient(model_path=model_path)
