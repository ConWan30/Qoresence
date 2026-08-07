"""Local distilled VLM stub — offline <100ms brain.

Tries ONNX model at models/qoresence-vlm-distilled.onnx; falls back to
lightweight heuristic that still returns a valid VisualContext.
Interface mirrors VLMClient.analyze_frame so swapping is trivial.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from qoresence.vision.scoreboard_extractor import extract_football_scoreboard
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext

try:
    from qoresence.core import (
        GameProfileId,
        get_game_profile,
        normalize_game_profile,
    )
except Exception:
    # Allow local_vlm to be imported in minimal test environments.
    GameProfileId = None  # type: ignore[misc,assignment]
    get_game_profile = None  # type: ignore[misc,assignment]
    normalize_game_profile = None  # type: ignore[misc,assignment]

log = logging.getLogger(__name__)
DEFAULT_ONNX = Path("models/qoresence-vlm-distilled.onnx")


def _is_football_profile(game_profile: str | object | None) -> bool:
    """Return True if the supplied profile is a football category."""
    if game_profile is None:
        return False
    s = str(game_profile).lower().strip()
    if s == "football":
        return True
    if s in (
        "ncaa_football_27",
        "ncaa",
        "college_football",
        "college_football_27",
        "ea_sports_college_football_27",
        "ncaa_27",
        "madden_27",
        "madden_2027",
    ):
        return True
    if GameProfileId is not None and isinstance(game_profile, GameProfileId):
        try:
            return get_game_profile(game_profile).category == "football"
        except Exception:
            return game_profile == GameProfileId.NCAA_FOOTBALL_27
    if normalize_game_profile is not None:
        try:
            canonical = normalize_game_profile(game_profile)
            return get_game_profile(canonical).category == "football"
        except Exception:
            pass
    return False


class LocalVLMClient:
    def __init__(
        self,
        model_path: str | Path | None = None,
        fallback: str = "heuristic",
        game_profile: str | object | None = None,
        scoreboard_ocr: bool | None = None,
    ):
        self.model_path = Path(model_path) if model_path else DEFAULT_ONNX
        self.fallback = fallback
        self.game_profile = game_profile
        # None = auto (football + min frame size); False = never; True = always when football.
        # Heuristic mode used to skip OCR entirely when ONNX was missing — that left
        # home_score/quarter/down null forever on live --play without distilled weights.
        self.scoreboard_ocr = scoreboard_ocr
        self._onnx_sess = None
        self._available = False
        self._mode = "heuristic"
        self._stats = {"calls": 0, "avg_ms": 0.0, "ocr_calls": 0, "ocr_skips": 0}
        self._history: deque[VisualContext] = deque(maxlen=5)
        self._ocr_every_n = 1  # run OCR every N football frames (1 = every)
        self._football_n = 0
        self._try_load()

    def _try_load(self) -> None:
        if self.model_path.exists():
            try:
                import onnxruntime as ort  # type: ignore

                self._onnx_sess = ort.InferenceSession(
                    str(self.model_path), providers=["CPUExecutionProvider"]
                )
                self._available = True
                self._mode = "onnx"
                self.warmup()
                log.info(f"LocalVLM ONNX loaded and warmed: {self.model_path}")
                return
            except Exception as e:
                log.warning(f"LocalVLM ONNX load failed ({e}), using heuristic")
        self._available = False
        self._mode = "heuristic"

    def is_available(self) -> bool:
        return self._onnx_sess is not None

    def set_game_profile(self, game_profile: str | object | None) -> None:
        """Update the active game profile (e.g. 'ncaa_football_27')."""
        self.game_profile = game_profile

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

    def analyze_frame(
        self,
        frame: np.ndarray,
        prompt: str = "",
        game_profile: str | object | None = None,
    ) -> VisualContext | None:
        t0 = time.perf_counter()
        profile = game_profile if game_profile is not None else self.game_profile

        raw = self._classify(frame, profile)
        if raw is not None:
            raw = self._profile_guard(raw, profile)
            self._history.append(raw)

        ctx = self._smooth()

        # Scoreboard OCR for football — ONNX *or* heuristic. Previously gated on
        # `_onnx_sess is not None`, so heuristic-only live sessions never filled
        # home_score/quarter/down (Lens pill empty while game_state=gameplay).
        if ctx and ctx.game_category == GameCategory.FOOTBALL and self._should_run_scoreboard_ocr(
            frame
        ):
            self._football_n += 1
            if self._football_n % max(1, self._ocr_every_n) == 0:
                ctx = extract_football_scoreboard(frame, ctx)
                self._stats["ocr_calls"] = int(self._stats.get("ocr_calls", 0)) + 1
            else:
                self._stats["ocr_skips"] = int(self._stats.get("ocr_skips", 0)) + 1

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

    def _should_run_scoreboard_ocr(self, frame: np.ndarray) -> bool:
        """Gate expensive EasyOCR: allow heuristic football, skip tiny/test frames."""
        import os

        if self.scoreboard_ocr is False:
            return False
        if os.environ.get("QORESENCE_DISABLE_SCOREBOARD_OCR", "").strip() in {
            "1",
            "true",
            "yes",
        }:
            return False
        if frame is None or not hasattr(frame, "shape") or len(frame.shape) < 2:
            return False
        h, w = int(frame.shape[0]), int(frame.shape[1])
        # Unit-test synthetics and eye thumbnails stay under this; live HDMI is 720p+.
        if h < 480 or w < 640:
            return False
        # Explicit True → always; None/auto → football path for both onnx + heuristic.
        return True

    def analyze_frame_raw(
        self,
        frame: np.ndarray,
        prompt: str,
        timeout: float = 10,
        max_tokens: int = 300,
        game_profile: str | object | None = None,
    ) -> str | None:
        ctx = self.analyze_frame(frame, prompt, game_profile=game_profile)
        if ctx is None:
            return None
        import json

        return json.dumps(ctx.to_dict())

    def _classify(
        self, frame: np.ndarray, game_profile: str | object | None
    ) -> VisualContext | None:
        if self._onnx_sess is not None:
            ctx = self._onnx_infer(frame, game_profile)
            if ctx is not None:
                return ctx
        return self._heuristic(frame, game_profile)

    def _onnx_infer(
        self, frame: np.ndarray, game_profile: str | object | None = None
    ) -> VisualContext | None:
        try:
            inp = self._onnx_sess.get_inputs()[0]
            img = cv2.resize(frame, (224, 224))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            img = np.transpose(img, (2, 0, 1))[None]
            out = self._onnx_sess.run(None, {inp.name: img})
            logits = np.array(out[0]).flatten()
            n = len(logits)
            if n == 3:
                # expect logits [football, unknown, menu]
                cats = [GameCategory.FOOTBALL, GameCategory.UNKNOWN, GameCategory.UNKNOWN]
                states = [GameState.GAMEPLAY, GameState.UNKNOWN, GameState.MENU]
            elif n == 4:
                # legacy 4-class distilled model
                cats = [
                    GameCategory.FOOTBALL,
                    GameCategory.SHOOTER,
                    GameCategory.UNKNOWN,
                    GameCategory.UNKNOWN,
                ]
                states = [GameState.GAMEPLAY, GameState.GAMEPLAY, GameState.MENU, GameState.UNKNOWN]
            else:
                log.warning(f"ONNX output has unexpected class count: {n}")
                return None

            # softmax for calibrated confidence
            shifted = logits - np.max(logits)
            exp = np.exp(shifted)
            probs = exp / exp.sum()
            idx = int(np.argmax(probs))
            conf = float(probs[idx])
            ctx = VisualContext(game_state=states[idx], game_category=cats[idx], confidence=conf)
            # leave scores zero - caller fills via outcome
            return self._profile_guard(ctx, game_profile)
        except Exception as e:
            log.debug(f"ONNX infer failed: {e}")
            return None

    def _heuristic(
        self, frame: np.ndarray, game_profile: str | object | None = None
    ) -> VisualContext:
        # fast heuristic: luma + edge density + green-field ratio
        small = cv2.resize(frame, (160, 90))
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        # green field ~ hue 35-85
        green = cv2.inRange(hsv, np.array([35, 40, 40]), np.array([85, 255, 255]))
        green_ratio = float((green > 0).mean())
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 180)
        edge_density = float((edges > 0).mean())
        mean_luma = float(gray.mean())
        return self._classify_features(green_ratio, edge_density, mean_luma, game_profile)

    def _classify_features(
        self,
        green_ratio: float,
        edge_density: float,
        mean_luma: float,
        game_profile: str | object | None = None,
    ) -> VisualContext:
        """Heuristic classification from pre-computed frame features.

        Mirrors the logic in ``_heuristic`` so callers can test exact
        green/edge/luma thresholds without building a synthetic image.
        """
        has_scoreboard = mean_luma > 30 and edge_density > 0.02

        if _is_football_profile(game_profile):
            if green_ratio > 0.06 and has_scoreboard:
                return VisualContext(
                    game_state=GameState.GAMEPLAY,
                    game_category=GameCategory.FOOTBALL,
                    confidence=0.72,
                    frame_quality="ok",
                )
            if edge_density > 0.06 and green_ratio < 0.08:
                if mean_luma < 35:
                    return VisualContext(
                        game_state=GameState.MENU,
                        game_category=GameCategory.UNKNOWN,
                        confidence=0.45,
                        frame_quality="dark",
                    )
                return VisualContext(
                    game_state=GameState.UNKNOWN,
                    game_category=GameCategory.UNKNOWN,
                    confidence=0.38,
                    frame_quality="ok",
                )
            if mean_luma < 20:
                return VisualContext(
                    game_state=GameState.MENU,
                    game_category=GameCategory.UNKNOWN,
                    confidence=0.45,
                    frame_quality="dark",
                )
            return VisualContext(
                game_state=GameState.UNKNOWN,
                game_category=GameCategory.UNKNOWN,
                confidence=0.35,
                frame_quality="ok",
            )

        if green_ratio > 0.06 and has_scoreboard:
            return VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                confidence=0.72,
                frame_quality="ok",
            )
        if edge_density > 0.06 and green_ratio < 0.08:
            if mean_luma < 35:
                return VisualContext(
                    game_state=GameState.MENU,
                    game_category=GameCategory.UNKNOWN,
                    confidence=0.45,
                    frame_quality="dark",
                )
            return VisualContext(
                game_state=GameState.UNKNOWN,
                game_category=GameCategory.UNKNOWN,
                confidence=0.38,
                frame_quality="ok",
            )
        if mean_luma < 20:
            return VisualContext(
                game_state=GameState.MENU,
                game_category=GameCategory.UNKNOWN,
                confidence=0.45,
                frame_quality="dark",
            )
        return VisualContext(
            game_state=GameState.UNKNOWN,
            game_category=GameCategory.UNKNOWN,
            confidence=0.35,
            frame_quality="ok",
        )

    def _profile_guard(
        self,
        ctx: VisualContext,
        game_profile: str | object | None,
    ) -> VisualContext:
        """Block SHOOTER emission when the active profile is football."""
        if ctx is None:
            return ctx
        if _is_football_profile(game_profile) and ctx.game_category == GameCategory.SHOOTER:
            return VisualContext(
                game_state=GameState.UNKNOWN,
                game_category=GameCategory.UNKNOWN,
                confidence=0.38,
                frame_quality=ctx.frame_quality or "ok",
                raw_response=ctx.raw_response,
                frame_hash=ctx.frame_hash,
                details=ctx.details,
            )
        return ctx

    def _smooth(self) -> VisualContext | None:
        """Temporal hysteresis: require a 3/5 majority over recent history."""
        if not self._history:
            return None

        n = len(self._history)
        # ceil(3 * n / 5): 1,2,2,3,3 for n=1..5
        required = max(1, (3 * n + 4) // 5)

        from collections import Counter

        cat_counts = Counter(h.game_category for h in self._history)
        winner, winner_count = cat_counts.most_common(1)[0]

        if winner_count >= required:
            winning = [h for h in self._history if h.game_category == winner]
            state_counts = Counter(h.game_state for h in winning)
            state = state_counts.most_common(1)[0][0]
            conf = sum(h.confidence for h in winning) / len(winning)
            latest = winning[-1]
            return VisualContext(
                game_state=state,
                game_category=winner,
                confidence=conf,
                home_score=latest.home_score,
                away_score=latest.away_score,
                quarter=latest.quarter,
                down=latest.down,
                yards_to_go=latest.yards_to_go,
                possession=latest.possession,
                clock_seconds=latest.clock_seconds,
                play_clock=latest.play_clock,
                play_type=latest.play_type,
                field_position=latest.field_position,
                down_distance_text=latest.down_distance_text,
                health=latest.health,
                ammo=latest.ammo,
                score=latest.score,
                kills=latest.kills,
                deaths=latest.deaths,
                round_info=latest.round_info,
                enemies_visible=latest.enemies_visible,
                is_combat=latest.is_combat,
                is_moving=latest.is_moving,
                has_screen_tearing=latest.has_screen_tearing,
                has_lag_indicator=latest.has_lag_indicator,
                frame_quality=latest.frame_quality or "ok",
                raw_response=latest.raw_response,
                frame_hash=latest.frame_hash,
                details=latest.details,
            )

        # No majority: emit unknown but keep the last known state/quality if
        # available so the stream does not flip arbitrarily.
        last = self._history[-1]
        return VisualContext(
            game_state=GameState.UNKNOWN,
            game_category=GameCategory.UNKNOWN,
            confidence=0.35,
            frame_quality=last.frame_quality or "ok",
            raw_response=last.raw_response,
            frame_hash=last.frame_hash,
            details=last.details,
        )

    def cross_modal_check(self, frame: np.ndarray, other_modalities: dict) -> None:  # type: ignore[override]
        """Local brain has no cloud VLM — return inconclusive."""
        # Keep interface compatible with VLMClient so VisualRuntime/VisionStack can swap.
        return None


def create_local_vlm_client(
    model_path: str | Path | None = None,
    game_profile: str | object | None = None,
) -> LocalVLMClient:
    return LocalVLMClient(model_path=model_path, game_profile=game_profile)
