"""
Qoresence Game Auto-Detection Module

Autonomous game classification using VLM (vision-language model) and OCR
evidence. Maintains a sliding-window confidence score to determine whether
the user is playing NCAA College Football 27 or Call of Duty, emits a
canonical ``game_detected`` event, and can trigger a runtime profile switch
for the Outcome lobe.

Recursive learning is supported by writing every sample (frame hash, OCR
text, VLM response, detected label) to a JSONL file. Confirmed labels can
be fed back to update keyword weights over time.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Optional

import cv2
import numpy as np

try:
    import pytesseract
except ImportError:
    pytesseract = None

from qoresence.core import (
    GAME_PROFILE_ALIASES,
    GameProfileId,
    RetinaEventBus,
    SourceLobe,
    VisualConfig,
    clock_ns,
    get_game_profile,
)
from qoresence.core.types import EventType
from qoresence.lobes.visual import VLMClient
from qoresence.vision import VisionStack, VisionEvidence

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# VOCABULARY DIFFERENTIATOR
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class GameVocabulary:
    """Weighted terminology dictionary for a single game profile."""
    profile_id: GameProfileId
    display_name: str
    keywords: dict[str, float] = field(default_factory=dict)

    def score_text(self, text: str) -> float:
        """Return a weighted match score in [0, 1] for the given text."""
        if not text:
            return 0.0
        text_lower = text.lower()
        score = 0.0
        for keyword, weight in self.keywords.items():
            if keyword.lower() in text_lower:
                score += weight
        return min(score, 1.0)


NCAA_VOCABULARY = GameVocabulary(
    profile_id=GameProfileId.NCAA_FOOTBALL_27,
    display_name="NCAA College Football 27",
    keywords={
        # Football terminology
        "touchdown": 0.30,
        "field goal": 0.25,
        "quarterback": 0.25,
        "yard line": 0.20,
        "first down": 0.25,
        "down": 0.15,
        "interception": 0.20,
        "fumble": 0.20,
        "punt": 0.15,
        "kickoff": 0.15,
        "snap": 0.15,
        "possession": 0.15,
        "timeout": 0.10,
        "penalty": 0.15,
        "turnover": 0.15,
        "quarter": 0.10,
        "overtime": 0.10,
        # Identity
        "ncaa": 0.40,
        "college football": 0.35,
        # HUD / UI
        "play clock": 0.10,
        "game clock": 0.10,
        "scoreboard": 0.10,
        "to go": 0.15,
        "ball on": 0.15,
    },
)

COD_VOCABULARY = GameVocabulary(
    profile_id=GameProfileId.CALL_OF_DUTY,
    display_name="Call of Duty",
    keywords={
        # Shooter terminology
        "kill": 0.25,
        "death": 0.20,
        "eliminated": 0.25,
        "kill feed": 0.30,
        "assist": 0.15,
        "streak": 0.20,
        "loadout": 0.20,
        "operator": 0.20,
        "ammo": 0.10,
        "health": 0.10,
        "armor": 0.10,
        "mini map": 0.15,
        "ping": 0.10,
        "gulag": 0.25,
        # Identity
        "call of duty": 0.40,
        "warzone": 0.35,
        "modern warfare": 0.30,
        "black ops": 0.30,
        # Game modes
        "team deathmatch": 0.20,
        "domination": 0.15,
        "search and destroy": 0.20,
        "battle royale": 0.20,
        "battle pass": 0.10,
    },
)


# ──────────────────────────────────────────────────────────────────────────────
# EVIDENCE & LEARNING DATA
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DetectionEvidence:
    """A single piece of evidence (VLM or OCR)."""
    timestamp_ns: int
    source: str  # "vlm" or "ocr"
    profile_id: Optional[GameProfileId]
    confidence: float
    details: dict[str, Any]


@dataclass
class GameDetectionResult:
    """Fused detection result at a point in time."""
    profile_id: GameProfileId
    display_name: str
    confidence: float
    evidence_count: int
    vlm_confidence: float
    ocr_confidence: float
    motion_confidence: float
    timestamp_ns: int


@dataclass
class LearningSample:
    """One captured sample for recursive learning."""
    timestamp_ns: int
    frame_hash: str
    ocr_text: str
    vlm_response: str
    detected_profile: Optional[str]
    vlm_confidence: float
    ocr_confidence: float
    motion_camera: float = 0.0
    hud_regions: list[dict] = field(default_factory=list)
    labeled_profile: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# GAME AUTO-DETECTOR
# ──────────────────────────────────────────────────────────────────────────────

class GameAutoDetector:
    """
    Autonomous game detection using VLM + OCR evidence fusion.

    Runs in its own thread, polls a frame provider at a configured interval,
    fuses visual-language and text evidence over a sliding window, and emits a
    ``game_detected`` event once a profile is stable above ``confidence_threshold``.
    """

    def __init__(
        self,
        bus: RetinaEventBus,
        session_head_ns: int,
        vlm_client: Optional[VLMClient] = None,
        api_key: Optional[str] = None,
        model_endpoint: str = "https://integrate.api.nvidia.com/v1",
        model_name: str = "meta/llama-3.2-11b-vision-instruct",
        confidence_threshold: float = 0.65,
        stability_count: int = 2,
        evidence_window_s: float = 15.0,
        poll_interval_s: float = 3.0,
        vlm_weight: float = 0.6,
        ocr_weight: float = 0.4,
        motion_weight: float = 0.15,
        use_vision_stack: bool = True,
        ocr_provider: str = "easyocr",
        model_dir: Optional[Path] = None,
        learning_enabled: bool = False,
        learning_path: Optional[Path] = None,
        game_profile: GameProfileId = GameProfileId.NCAA_FOOTBALL_27,
    ):
        self.bus = bus
        self.session_head_ns = session_head_ns

        # VLM client: use provided, or create one from credentials, or None (OCR-only)
        if vlm_client is not None:
            self._vlm_client = vlm_client
        elif api_key:
            self._vlm_client = VLMClient(VisualConfig(
                enabled=True,
                api_key=api_key,
                model_endpoint=model_endpoint,
                model_name=model_name,
                frame_sample_rate=1,
                game_category="unknown",
            ))
        else:
            self._vlm_client = None

        self._confidence_threshold = confidence_threshold
        self._stability_count = stability_count
        self._evidence_window_s = evidence_window_s
        self._poll_interval_s = poll_interval_s
        self._vlm_weight = vlm_weight
        self._ocr_weight = ocr_weight
        self._motion_weight = motion_weight

        # Vision Stack: synchronized VLM + OCR + motion + HUD detection
        self._use_vision_stack = use_vision_stack and self._vlm_client is not None
        if self._use_vision_stack:
            from qoresence.vision import create_ocr_provider
            self._vision_stack = VisionStack(
                vlm_client=self._vlm_client,
                ocr_provider=create_ocr_provider(ocr_provider, vlm_client=self._vlm_client),
                enable_motion=True,
                enable_hud=True,
                model_dir=model_dir,
                game_profile=game_profile,
            )
        else:
            self._vision_stack = None

        self._frame_provider: Optional[Callable[[], Optional[np.ndarray]]] = None
        self._profile_switch_callback: Optional[Callable[[GameProfileId], None]] = None

        self._vocabularies: dict[GameProfileId, GameVocabulary] = {
            GameProfileId.NCAA_FOOTBALL_27: NCAA_VOCABULARY,
            GameProfileId.CALL_OF_DUTY: COD_VOCABULARY,
        }
        self._all_profiles = tuple(self._vocabularies.keys())

        self._evidence: Deque[DetectionEvidence] = deque()
        self._current_result: Optional[GameDetectionResult] = None
        self._last_emitted_profile: Optional[GameProfileId] = None
        self._consecutive_detections: int = 0

        self._learning_enabled = learning_enabled
        self._learning_path = learning_path or Path("game_detection_learning.jsonl")
        self._learning_samples: list[LearningSample] = []

        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def set_frame_provider(self, provider: Callable[[], Optional[np.ndarray]]) -> None:
        """Set frame provider (e.g., streamer or screen lobe)."""
        self._frame_provider = provider

    def set_profile_switch_callback(self, callback: Callable[[GameProfileId], None]) -> None:
        """Set callback invoked when a new game is detected."""
        self._profile_switch_callback = callback

    def start(self) -> bool:
        """Start detection loop in a background thread."""
        if self._running:
            log.warning("GameAutoDetector already running")
            return True

        if self._frame_provider is None:
            log.warning("No frame provider set - game detection will not run")
            return False

        self._running = True
        # Models warm up lazily on first use so start() returns immediately
        self._thread = threading.Thread(target=self._run_loop, name="qoresence-game-detect", daemon=True)
        self._thread.start()

        log.info(
            f"GameAutoDetector started: threshold={self._confidence_threshold}, "
            f"window={self._evidence_window_s}s, poll={self._poll_interval_s}s, "
            f"learning={self._learning_enabled}"
        )
        return True

    def stop(self) -> None:
        """Stop detection loop and persist learning data."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

        if self._vision_stack:
            self._vision_stack.stop()

        if self._learning_enabled:
            self._save_learning_data()

        log.info("GameAutoDetector stopped")

    def is_running(self) -> bool:
        return self._running

    def get_current_detection(self) -> Optional[GameDetectionResult]:
        with self._lock():
            return self._current_result

    def get_recent_evidence(self, n: int = 10) -> list[DetectionEvidence]:
        with self._lock():
            return list(self._evidence)[-n:]

    def label_last_detection(self, profile_id: GameProfileId) -> None:
        """Apply a user-confirmed label to the most recent unlabeled sample."""
        if not self._learning_enabled or not self._learning_samples:
            return

        # Label the most recent unlabeled sample
        for sample in reversed(self._learning_samples):
            if sample.labeled_profile is None:
                sample.labeled_profile = profile_id.value
                self._update_vocabulary_weights(sample, profile_id)
                break

        self._save_learning_data()

    # ──────────────────────────────────────────────────────────────────────────
    # RUNTIME LOOP
    # ──────────────────────────────────────────────────────────────────────────

    def _lock(self):
        # Lazy lock to avoid __init__ ordering issues
        if not hasattr(self, "_evidence_lock"):
            self._evidence_lock = threading.RLock()
        return self._evidence_lock

    def _run_loop(self) -> None:
        """Main detection loop."""
        while self._running:
            loop_start = time.time()

            try:
                self._tick()
            except Exception as e:
                log.warning(f"Game detection tick failed: {e}")

            elapsed = time.time() - loop_start
            sleep_time = self._poll_interval_s - elapsed
            if sleep_time > 0 and self._running:
                time.sleep(sleep_time)

    def _tick(self) -> None:
        """Collect evidence, fuse, and emit if stable."""
        frame = self._get_frame()
        if frame is None:
            return

        if self._use_vision_stack and self._vision_stack:
            self._tick_vision_stack(frame)
        else:
            self._tick_legacy(frame)

    def _tick_vision_stack(self, frame: np.ndarray) -> None:
        """Use the synchronized VisionStack to collect all evidence."""
        vision = self._vision_stack.analyze(frame)
        if vision is None:
            return

        with self._lock():
            now_ns = clock_ns()

            # VLM game evidence
            if vision.vlm_game is not None:
                vlm_evidence = DetectionEvidence(
                    timestamp_ns=vision.timestamp_ns,
                    source="vlm",
                    profile_id=vision.vlm_game,
                    confidence=vision.vlm_confidence,
                    details={"raw_response": vision.vlm_response, "hud_regions": len(vision.hud_regions)},
                )
                self._evidence.append(vlm_evidence)

            # OCR vocabulary evidence
            ocr_evidence = self._score_ocr_text(vision.timestamp_ns, vision.ocr_text, vision.ocr_provider)
            if ocr_evidence:
                self._evidence.append(ocr_evidence)

            # Motion evidence
            if vision.motion:
                motion_evidence = self._motion_evidence(vision.timestamp_ns, vision.motion)
                if motion_evidence:
                    self._evidence.append(motion_evidence)

            if self._learning_enabled:
                self._record_learning_sample(frame, vision)

            # Emit structured visual context for the outcome lobe
            if vision.visual_context is not None:
                try:
                    self.bus.emit_raw(
                        source_lobe=SourceLobe.VISUAL,
                        event_type=EventType.VISUAL_CONTEXT,
                        payload=vision.visual_context.to_dict(),
                        session_head_ns=self.session_head_ns,
                    )
                except Exception as e:
                    log.warning(f"Failed to emit visual_context: {e}")

            # Trim old evidence
            self._prune_evidence(now_ns)

            # Fuse into a result
            result = self._fuse_evidence(now_ns)
            self._current_result = result

        self._maybe_emit_and_switch(result)

    def _tick_legacy(self, frame: np.ndarray) -> None:
        """Legacy path: separate VLM + Tesseract OCR."""
        vlm_evidence = self._collect_vlm_evidence(frame)
        ocr_evidence = self._collect_ocr_evidence(frame)

        with self._lock():
            now_ns = clock_ns()

            if vlm_evidence:
                self._evidence.append(vlm_evidence)

            if ocr_evidence:
                self._evidence.append(ocr_evidence)

            self._prune_evidence(now_ns)
            result = self._fuse_evidence(now_ns)
            self._current_result = result

        self._maybe_emit_and_switch(result)

    def _maybe_emit_and_switch(self, result: Optional[GameDetectionResult]) -> None:
        if result is None:
            log.debug("_maybe_emit_and_switch: no result")
            return

        log.debug(
            f"_maybe_emit_and_switch: profile={result.profile_id.value}, "
            f"confidence={result.confidence:.3f}, threshold={self._confidence_threshold}, "
            f"evidence={result.evidence_count}"
        )

        if result.confidence >= self._confidence_threshold:
            if result.profile_id == self._last_emitted_profile:
                self._consecutive_detections += 1
            else:
                self._consecutive_detections = 1
                self._last_emitted_profile = result.profile_id

            # Emit once when we first reach stability, then again only after
            # confidence drops and recovers (or the profile changes).
            if self._consecutive_detections == self._stability_count:
                self._emit_game_detected(result)
                if self._profile_switch_callback:
                    try:
                        self._profile_switch_callback(result.profile_id)
                    except Exception as e:
                        log.warning(f"Profile switch callback failed: {e}")
        else:
            # Confidence lost; require a fresh stable streak before re-emitting
            self._consecutive_detections = 0

    # ──────────────────────────────────────────────────────────────────────────
    # EVIDENCE COLLECTION
    # ──────────────────────────────────────────────────────────────────────────

    def _get_frame(self) -> Optional[np.ndarray]:
        if self._frame_provider is None:
            return None
        try:
            return self._frame_provider()
        except Exception as e:
            log.warning(f"Frame provider error: {e}")
            return None

    def _collect_vlm_evidence(self, frame: np.ndarray) -> Optional[DetectionEvidence]:
        if self._vlm_client is None:
            return None

        prompt = (
            "Identify the video game shown in this image. "
            "Choose exactly one of these labels: ncaa_football_27, call_of_duty, menu, unknown.\n\n"
            "Output format (no explanation):\n"
            "GAME: ncaa_football_27\n"
            "CONFIDENCE: 0.95\n\n"
            "Rules:\n"
            "- Pick 'menu' only for the main menu or settings screens, not for an in-game pause overlay.\n"
            "- Pick 'unknown' when the image is black, blurry, or unrecognizable.\n"
            "- Only return the two lines above."
        )

        raw_response = self._vlm_client.analyze_frame_raw(frame, prompt)
        if raw_response is None:
            return None

        # Parse structured response
        profile, confidence = self._parse_game_response(raw_response)

        details = {
            "raw_response": raw_response,
            "latency_ms": 0.0,
        }

        return DetectionEvidence(
            timestamp_ns=clock_ns(),
            source="vlm",
            profile_id=profile,
            confidence=confidence,
            details=details,
        )

    def _collect_ocr_evidence(self, frame: np.ndarray) -> Optional[DetectionEvidence]:
        """Run OCR on a downscaled grayscale copy and score both vocabularies."""
        if pytesseract is None:
            return None

        try:
            h, w = frame.shape[:2]
            scale = 640 / max(h, w)
            small = cv2.resize(frame, (int(w * scale), int(h * scale)))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            text = pytesseract.image_to_string(binary, config="--psm 6").strip()
            if not text:
                return None

            # Score each vocabulary
            best_profile: Optional[GameProfileId] = None
            best_score = 0.0
            for profile_id, vocab in self._vocabularies.items():
                score = vocab.score_text(text)
                if score > best_score:
                    best_score = score
                    best_profile = profile_id

            # If no clear vocabulary match, fall back to "unknown" with low confidence
            if best_profile is None or best_score < 0.05:
                return DetectionEvidence(
                    timestamp_ns=clock_ns(),
                    source="ocr",
                    profile_id=None,
                    confidence=0.3,
                    details={"ocr_text": text[:500], "scores": {p.value: 0.0 for p in self._vocabularies}},
                )

            return DetectionEvidence(
                timestamp_ns=clock_ns(),
                source="ocr",
                profile_id=best_profile,
                confidence=min(best_score, 1.0),
                details={"ocr_text": text[:500], "scores": {p.value: v.score_text(text) for p, v in self._vocabularies.items()}},
            )

        except Exception as e:
            log.warning(f"OCR evidence collection failed: {e}")
            return None

    def _score_ocr_text(self, timestamp_ns: int, text: str, provider: str) -> Optional[DetectionEvidence]:
        """Score OCR text against game vocabularies and return evidence."""
        if not text:
            return None

        best_profile: Optional[GameProfileId] = None
        best_score = 0.0
        for profile_id, vocab in self._vocabularies.items():
            score = vocab.score_text(text)
            if score > best_score:
                best_score = score
                best_profile = profile_id

        if best_profile is None or best_score < 0.05:
            return None

        return DetectionEvidence(
            timestamp_ns=timestamp_ns,
            source="ocr",
            profile_id=best_profile,
            confidence=min(best_score, 1.0),
            details={
                "ocr_text": text[:500],
                "provider": provider,
                "scores": {p.value: v.score_text(text) for p, v in self._vocabularies.items()},
            },
        )

    def _motion_evidence(self, timestamp_ns: int, motion: Any) -> Optional[DetectionEvidence]:
        """Convert motion analysis into a detection evidence."""
        cam = motion.camera_velocity
        obj = motion.object_velocity

        # Simple heuristic: high camera/object velocity is more shooter-like;
        # low, steady camera is more football/broadcast-like.
        # Normalize against a soft ceiling.
        ceiling = 20.0
        shooter_score = min(1.0, (cam + obj) / (2 * ceiling))
        football_score = 1.0 - shooter_score

        if shooter_score > football_score:
            profile_id = GameProfileId.CALL_OF_DUTY
            confidence = shooter_score
        else:
            profile_id = GameProfileId.NCAA_FOOTBALL_27
            confidence = football_score

        # Low total motion is ambiguous; reduce confidence
        total = cam + obj
        if total < 1.0:
            confidence *= 0.5

        return DetectionEvidence(
            timestamp_ns=timestamp_ns,
            source="motion",
            profile_id=profile_id,
            confidence=confidence,
            details={
                "camera_velocity": cam,
                "object_velocity": obj,
                "motion_class_hint": motion.motion_class_hint,
            },
        )

    # ──────────────────────────────────────────────────────────────────────────
    # FUSION & EMIT
    # ──────────────────────────────────────────────────────────────────────────

    def _prune_evidence(self, now_ns: int) -> None:
        cutoff = now_ns - int(self._evidence_window_s * 1e9)
        while self._evidence and self._evidence[0].timestamp_ns < cutoff:
            self._evidence.popleft()

    def _fuse_evidence(self, now_ns: int) -> GameDetectionResult:
        """Combine VLM, OCR and motion evidence into a single detection result."""
        if not self._evidence:
            return GameDetectionResult(
                profile_id=GameProfileId.NCAA_FOOTBALL_27,
                display_name=self._vocabularies[GameProfileId.NCAA_FOOTBALL_27].display_name,
                confidence=0.0,
                evidence_count=0,
                vlm_confidence=0.0,
                ocr_confidence=0.0,
                motion_confidence=0.0,
                timestamp_ns=now_ns,
            )

        # Accumulate per-profile scores
        scores: dict[GameProfileId, float] = {p: 0.0 for p in self._all_profiles}
        counts: dict[str, int] = {"vlm": 0, "ocr": 0, "motion": 0}
        vlm_total = 0.0
        ocr_total = 0.0
        motion_total = 0.0

        for ev in self._evidence:
            if ev.profile_id in scores:
                if ev.source == "vlm":
                    scores[ev.profile_id] += ev.confidence * self._vlm_weight
                    vlm_total += ev.confidence
                    counts["vlm"] += 1
                elif ev.source == "ocr":
                    scores[ev.profile_id] += ev.confidence * self._ocr_weight
                    ocr_total += ev.confidence
                    counts["ocr"] += 1
                elif ev.source == "motion":
                    scores[ev.profile_id] += ev.confidence * self._motion_weight
                    motion_total += ev.confidence
                    counts["motion"] += 1

        # Normalize and choose the highest
        best_profile = max(scores, key=scores.get)  # type: ignore[arg-type]
        raw_score = scores[best_profile]

        # Confidence is the raw score divided by total weight count to keep it in [0,1]
        total_weight = (
            counts["vlm"] * self._vlm_weight
            + counts["ocr"] * self._ocr_weight
            + counts["motion"] * self._motion_weight
        )
        confidence = (raw_score / total_weight) if total_weight > 0 else 0.0

        # Track profile-specific confidences
        vlm_confidence = (vlm_total / counts["vlm"]) if counts["vlm"] else 0.0
        ocr_confidence = (ocr_total / counts["ocr"]) if counts["ocr"] else 0.0
        motion_confidence = (motion_total / counts["motion"]) if counts["motion"] else 0.0

        return GameDetectionResult(
            profile_id=best_profile,
            display_name=self._vocabularies[best_profile].display_name,
            confidence=confidence,
            evidence_count=len(self._evidence),
            vlm_confidence=vlm_confidence,
            ocr_confidence=ocr_confidence,
            timestamp_ns=now_ns,
            motion_confidence=motion_confidence,
        )

    def _emit_game_detected(self, result: GameDetectionResult) -> None:
        """Emit canonical game_detected event to the bus."""
        log.info(
            f"Emitting game_detected: profile={result.profile_id.value}, "
            f"confidence={result.confidence:.3f}, evidence_count={result.evidence_count}"
        )
        try:
            self.bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type=EventType.GAME_DETECTED,
                payload={
                    "profile_id": result.profile_id.value,
                    "display_name": result.display_name,
                    "confidence": result.confidence,
                    "evidence_count": result.evidence_count,
                    "vlm_confidence": result.vlm_confidence,
                    "ocr_confidence": result.ocr_confidence,
                    "motion_confidence": result.motion_confidence,
                },
                session_head_ns=self.session_head_ns,
            )
        except Exception as e:
            log.warning(f"Failed to emit game_detected event: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # LEARNING
    # ──────────────────────────────────────────────────────────────────────────

    def _record_learning_sample(self, frame: np.ndarray, vision: VisionEvidence) -> None:
        """Append a learning sample to in-memory buffer."""
        # Compute a stable hash of the downscaled frame
        small = cv2.resize(frame, (160, 90))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        frame_hash = hashlib.sha256(gray.tobytes()).hexdigest()[:16]

        motion_camera = 0.0
        if vision.motion:
            motion_camera = vision.motion.camera_velocity

        sample = LearningSample(
            timestamp_ns=clock_ns(),
            frame_hash=frame_hash,
            ocr_text=vision.ocr_text,
            vlm_response=vision.vlm_response,
            detected_profile=vision.vlm_game.value if vision.vlm_game else None,
            vlm_confidence=vision.vlm_confidence,
            ocr_confidence=vision.ocr_confidence,
            motion_camera=motion_camera,
            hud_regions=[{"label": r.label, "x1": r.x1, "y1": r.y1, "x2": r.x2, "y2": r.y2, "conf": r.confidence} for r in vision.hud_regions],
        )

        self._learning_samples.append(sample)

    def _update_vocabulary_weights(self, sample: LearningSample, confirmed: GameProfileId) -> None:
        """Boost keyword weights that appear in a confirmed sample."""
        if confirmed not in self._vocabularies:
            return

        text = (sample.ocr_text + " " + sample.vlm_response).lower()
        vocab = self._vocabularies[confirmed]
        for keyword, weight in list(vocab.keywords.items()):
            if keyword in text:
                vocab.keywords[keyword] = min(weight + 0.05, 1.0)

    def _save_learning_data(self) -> None:
        """Persist learning samples to JSONL."""
        try:
            with self._learning_path.open("a", encoding="utf-8") as f:
                for sample in self._learning_samples:
                    f.write(json.dumps({
                        "timestamp_ns": sample.timestamp_ns,
                        "frame_hash": sample.frame_hash,
                        "ocr_text": sample.ocr_text,
                        "vlm_response": sample.vlm_response,
                        "detected_profile": sample.detected_profile,
                        "vlm_confidence": sample.vlm_confidence,
                        "ocr_confidence": sample.ocr_confidence,
                        "motion_camera": sample.motion_camera,
                        "hud_regions": sample.hud_regions,
                        "labeled_profile": sample.labeled_profile,
                    }, separators=(",", ":")) + "\n")
            self._learning_samples.clear()
        except Exception as e:
            log.warning(f"Failed to save game detection learning data: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # UTILITIES
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_game_response(raw: str) -> tuple[Optional[GameProfileId], float]:
        """Parse VLM response in GAME: <label> CONFIDENCE: <number> format."""
        if not raw:
            return None, 0.0

        text = raw.strip()

        # Find the first GAME: line and extract the label
        game_match = re.search(r"GAME:\s*([\w\_\-]+)", text, re.IGNORECASE)
        conf_match = re.search(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", text, re.IGNORECASE)

        if not game_match:
            return None, 0.0

        label = game_match.group(1).lower().strip()

        # Reject if the model echoed the option list with pipes
        valid_labels = {"ncaa_football_27", "call_of_duty", "menu", "unknown"}
        valid_labels |= set(GAME_PROFILE_ALIASES.keys())
        if "|" in label or label not in valid_labels:
            return None, 0.0

        confidence = float(conf_match.group(1)) if conf_match else 0.7

        try:
            profile_id = get_game_profile(label).profile_id
        except ValueError:
            return None, 0.0
        return profile_id, confidence


def create_game_detector(
    bus: RetinaEventBus,
    session_head_ns: int,
    vlm_client: Optional[VLMClient] = None,
    **kwargs,
) -> GameAutoDetector:
    """Factory for GameAutoDetector."""
    return GameAutoDetector(bus, session_head_ns, vlm_client=vlm_client, **kwargs)
