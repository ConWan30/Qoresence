"""
Qoresence Outcome Lobe — Phase 5

Game-specific event detection and emission.
Supports NCAA Football 27 and Call of Duty as first-class profiles.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional

import cv2
import numpy as np

from qoresence.core import (
    RetinaEventBus,
    SourceLobe,
    EventType,
    clock_ns,
    OutcomeConfig,
    GameProfileId,
    GameProfile,
    get_game_profile,
    NCAA_FOOTBALL_27_PROFILE,
    CALL_OF_DUTY_PROFILE,
)
from qoresence.vision.ocr_providers import EasyOCRProvider

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# OUTCOME EVENT DEFINITIONS PER PROFILE
# ──────────────────────────────────────────────────────────────────────────────

# NCAA Football 27 outcome fields mapping to detector names
NCAA_DETECTORS = {
    "snap": ["ball_snapped", "center_qb_exchange"],
    "down_advanced": ["down_marker_change", "play_result"],
    "first_down": ["first_down_marker", "chains_move"],
    "score_changed": ["scoreboard_delta", "touchdown", "field_goal", "safety"],
    "playclock_reset": ["play_clock_reset", "new_play_clock"],
    "quarter_changed": ["quarter_transition", "clock_hits_zero"],
    "possession_changed": ["turnover", "punt", "downs_turnover", "kickoff"],
    "timeout_called": ["timeout_indicator", "team_timeout"],
    "penalty": ["penalty_flag", "penalty_yards"],
    "turnover": ["interception", "fumble_recovery", "turnover_on_downs"],
}

# Call of Duty outcome fields mapping
COD_DETECTORS = {
    "kill": ["kill_feed", "elimination"],
    "death": ["death_cam", "eliminated"],
    "assist": ["assist_feed", "assist_count"],
    "streak": ["streak_counter", "streak_reward"],
    "objective_capture": ["flag_capture", "point_capture", "bomb_plant"],
    "objective_defend": ["defend_kill", "defend_point"],
    "round_start": ["round_timer", "buy_phase_end"],
    "round_end": ["round_winner", "round_timer_expired"],
    "match_start": ["match_begin", "loading_complete"],
    "match_end": ["match_winner", "final_scoreboard"],
}


@dataclass
class DetectionResult:
    """Result of a single detector check."""
    event_name: str
    detected: bool
    confidence: float
    fields: dict[str, Any]


# ──────────────────────────────────────────────────────────────────────────────
# OCR REGIONS (normalized coordinates for each profile)
# ──────────────────────────────────────────────────────────────────────────────

NCAA_OCR_REGIONS = {
    "scoreboard": (0.15, 0.02, 0.7, 0.08),      # Top center score
    "down_distance": (0.05, 0.10, 0.25, 0.06),  # Top left down/distance
    "possession": (0.75, 0.02, 0.2, 0.04),      # Top right possession
    "play_clock": (0.45, 0.08, 0.1, 0.04),      # Play clock
    "game_clock": (0.85, 0.02, 0.1, 0.04),      # Game clock
    "quarter": (0.05, 0.02, 0.1, 0.04),         # Quarter indicator
    "yard_line": (0.3, 0.90, 0.4, 0.06),        # Bottom field position
}

COD_OCR_REGIONS = {
    "kill_feed": (0.7, 0.15, 0.25, 0.6),        # Right side kill feed
    "score": (0.05, 0.02, 0.2, 0.05),           # Top left score
    "health": (0.05, 0.90, 0.2, 0.05),          # Bottom left health
    "ammo": (0.75, 0.90, 0.2, 0.05),            # Bottom right ammo
    "mini_map": (0.75, 0.02, 0.2, 0.15),        # Top right mini-map
    "streak": (0.35, 0.02, 0.3, 0.05),          # Top center streak
}


# ──────────────────────────────────────────────────────────────────────────────
# OUTCOME RUNTIME
# ──────────────────────────────────────────────────────────────────────────────

class OutcomeRuntime:
    """
    Game-specific outcome event detector.

    - Loads profile from OutcomeConfig
    - Polls frames at configured interval
    - Runs detectors (OCR, template matching, color detection)
    - Emits outcome_event onto RetinaEventBus
    """

    def __init__(
        self,
        config: OutcomeConfig,
        bus: RetinaEventBus,
        session_head_ns: int,
        frame_provider: Optional[Callable[[], Optional[np.ndarray]]] = None,
    ):
        self.config = config
        self.bus = bus
        self.session_head_ns = session_head_ns

        # Optional frame provider (e.g., from streamer lobe)
        self._frame_provider = frame_provider

        # Profile
        self._profile: GameProfile = get_game_profile(config.game_profile)
        self._detectors = self._build_detectors()

        # OCR
        self._ocr_regions = self._get_ocr_regions()
        self._ocr_provider = EasyOCRProvider()

        # Per-frame OCR cache: avoid running EasyOCR once per region
        self._last_frame_id: Optional[int] = None
        self._last_ocr_bboxes: list = []

        # State
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._prev_fields: dict[str, Any] = {}
        self._detections_count = 0
        self._start_time = 0.0

        # Confidence threshold
        self._confidence_threshold = config.confidence_threshold

        # Presence callback (for fusion engine)
        self._presence_callback: Optional[callable] = None

        # Track last state for cross-modal verification
        self._last_event = None
        self._home_score = 0
        self._away_score = 0

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start detection loop."""
        if self._running:
            log.warning("OutcomeRuntime already running")
            return True

        if self._frame_provider is None:
            log.warning("No frame provider set - outcome lobe will not detect events")

        # Warm-up OCR model once (downloaded models are reused)
        try:
            self._ocr_provider.warmup()
        except Exception as e:
            log.warning(f"Outcome OCR warm-up failed: {e}")

        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._run_loop, name="qoresence-outcome", daemon=True)
        self._thread.start()

        log.info(f"Outcome lobe started: profile={self._profile.profile_id.value}, "
                 f"interval={self.config.poll_interval_s}s, method={self.config.detection_method}")
        return True

    def stop(self) -> None:
        """Stop detection loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        log.info("Outcome lobe stopped")

    def is_running(self) -> bool:
        return self._running

    def set_presence_callback(self, callback: callable) -> None:
        """Set callback for presence status updates (for fusion engine)."""
        self._presence_callback = callback

    def get_last_state(self) -> dict:
        """Get last outcome state for cross-modal verification."""
        return {
            'last_event': self._last_event if hasattr(self, '_last_event') else None,
            'home_score': self._home_score if hasattr(self, '_home_score') else 0,
            'away_score': self._away_score if hasattr(self, '_away_score') else 0,
        }

    def set_frame_provider(self, provider: Callable[[], Optional[np.ndarray]]) -> None:
        """Set frame provider callback (e.g., from streamer lobe)."""
        self._frame_provider = provider

    def set_game_profile(self, profile_id: GameProfileId) -> None:
        """Switch the active game profile and rebuild detectors at runtime."""
        if self.config.game_profile == profile_id:
            return

        self.config = replace(self.config, game_profile=profile_id)
        self._profile = get_game_profile(profile_id)
        self._detectors = self._build_detectors()
        self._ocr_regions = self._get_ocr_regions()
        log.info(f"Outcome lobe switched to profile: {profile_id.value}")

    # ──────────────────────────────────────────────────────────────────────────
    # DETECTOR SETUP
    # ──────────────────────────────────────────────────────────────────────────

    def _build_detectors(self) -> dict[str, Callable[[np.ndarray], DetectionResult]]:
        """Build detector functions for the active profile."""
        detectors = {}

        if self._profile.profile_id == GameProfileId.NCAA_FOOTBALL_27:
            detectors = self._build_ncaa_detectors()
        elif self._profile.profile_id == GameProfileId.CALL_OF_DUTY:
            detectors = self._build_cod_detectors()

        return detectors

    def _build_ncaa_detectors(self) -> dict[str, Callable]:
        """Build NCAA Football 27 specific detectors."""
        return {
            "snap": self._detect_snap,
            "down_advanced": self._detect_down_advanced,
            "first_down": self._detect_first_down,
            "score_changed": self._detect_score_changed,
            "playclock_reset": self._detect_playclock_reset,
            "quarter_changed": self._detect_quarter_changed,
            "possession_changed": self._detect_possession_changed,
            "timeout_called": self._detect_timeout,
            "penalty": self._detect_penalty,
            "turnover": self._detect_turnover,
        }

    def _build_cod_detectors(self) -> dict[str, Callable]:
        """Build Call of Duty specific detectors."""
        return {
            "kill": self._detect_kill,
            "death": self._detect_death,
            "assist": self._detect_assist,
            "streak": self._detect_streak,
            "objective_capture": self._detect_objective_capture,
            "objective_defend": self._detect_objective_defend,
            "round_start": self._detect_round_start,
            "round_end": self._detect_round_end,
            "match_start": self._detect_match_start,
            "match_end": self._detect_match_end,
        }

    def _get_ocr_regions(self) -> dict[str, tuple]:
        """Get OCR regions for active profile."""
        if self._profile.profile_id == GameProfileId.NCAA_FOOTBALL_27:
            return NCAA_OCR_REGIONS
        elif self._profile.profile_id == GameProfileId.CALL_OF_DUTY:
            return COD_OCR_REGIONS
        return {}

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN LOOP
    # ──────────────────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Main detection loop."""
        # Emit session_start
        self._emit_session_start()

        while self._running:
            loop_start = time.time()

            # Get frame
            frame = self._get_frame()
            if frame is not None:
                self._process_frame(frame)

            # Pace
            elapsed = time.time() - loop_start
            sleep_time = self.config.poll_interval_s - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Session end
        self._emit_session_end()

    def _get_frame(self) -> Optional[np.ndarray]:
        """Get frame from provider."""
        if self._frame_provider:
            try:
                return self._frame_provider()
            except Exception as e:
                log.warning(f"Frame provider error: {e}")
        return None

    def _process_frame(self, frame: np.ndarray) -> None:
        """Run all detectors on frame."""
        self._refresh_ocr_cache(frame)

        for event_name, detector in self._detectors.items():
            try:
                result = detector(frame)
                if result.detected and result.confidence >= self._confidence_threshold:
                    self._emit_outcome_event(result)
                    self._detections_count += 1
            except Exception as e:
                log.warning(f"Detector {event_name} error: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # NCAA FOOTBALL 27 DETECTORS (placeholder implementations)
    # ──────────────────────────────────────────────────────────────────────────

    def _detect_snap(self, frame: np.ndarray) -> DetectionResult:
        """Detect snap event - ball movement at center."""
        # Placeholder: detect sudden motion in center-bottom region
        h, w = frame.shape[:2]
        center_region = frame[int(h*0.5):int(h*0.7), int(w*0.3):int(w*0.7)]
        # In real impl: optical flow on ball, center-QB exchange detection
        return DetectionResult("snap", False, 0.0, {})

    def _detect_down_advanced(self, frame: np.ndarray) -> DetectionResult:
        """Detect down marker change."""
        # OCR down/distance region
        down_text = self._ocr_region(frame, "down_distance")
        if down_text and down_text != self._prev_fields.get("down_text"):
            return DetectionResult("down_advanced", True, 0.8, {"down_text": down_text})
        return DetectionResult("down_advanced", False, 0.0, {})

    def _detect_first_down(self, frame: np.ndarray) -> DetectionResult:
        """Detect first down achieved."""
        # Look for "1st" or chain movement
        down_text = self._ocr_region(frame, "down_distance")
        if down_text and "1st" in down_text.lower():
            return DetectionResult("first_down", True, 0.85, {"down_text": down_text})
        return DetectionResult("first_down", False, 0.0, {})

    def _detect_score_changed(self, frame: np.ndarray) -> DetectionResult:
        """Detect scoreboard change."""
        score_text = self._ocr_region(frame, "scoreboard")
        if score_text:
            # Parse home/away scores
            parts = score_text.replace(" ", "").split("-")
            if len(parts) == 2:
                try:
                    home = int(parts[0])
                    away = int(parts[1])
                    prev = self._prev_fields.get("score", (0, 0))
                    if (home, away) != prev:
                        return DetectionResult("score_changed", True, 0.9, {
                            "home_score": home,
                            "away_score": away,
                            "prev_home": prev[0],
                            "prev_away": prev[1],
                        })
                except ValueError:
                    pass
        return DetectionResult("score_changed", False, 0.0, {})

    def _detect_playclock_reset(self, frame: np.ndarray) -> DetectionResult:
        """Detect play clock reset to 25/40."""
        clock_text = self._ocr_region(frame, "play_clock")
        if clock_text:
            try:
                val = int(''.join(filter(str.isdigit, clock_text)))
                if val in (25, 40) and self._prev_fields.get("play_clock") != val:
                    return DetectionResult("playclock_reset", True, 0.8, {"play_clock": val})
            except ValueError:
                pass
        return DetectionResult("playclock_reset", False, 0.0, {})

    def _detect_quarter_changed(self, frame: np.ndarray) -> DetectionResult:
        """Detect quarter transition."""
        q_text = self._ocr_region(frame, "quarter")
        if q_text:
            try:
                q = int(''.join(filter(str.isdigit, q_text)))
                if q != self._prev_fields.get("quarter"):
                    return DetectionResult("quarter_changed", True, 0.9, {"quarter": q})
            except ValueError:
                pass
        return DetectionResult("quarter_changed", False, 0.0, {})

    def _detect_possession_changed(self, frame: np.ndarray) -> DetectionResult:
        """Detect possession change (turnover, punt, etc.)."""
        poss_text = self._ocr_region(frame, "possession")
        if poss_text and poss_text != self._prev_fields.get("possession"):
            return DetectionResult("possession_changed", True, 0.75, {
                "possession": poss_text,
                "prev_possession": self._prev_fields.get("possession"),
            })
        return DetectionResult("possession_changed", False, 0.0, {})

    def _detect_timeout(self, frame: np.ndarray) -> DetectionResult:
        """Detect timeout indicator."""
        # Look for timeout icon/text
        return DetectionResult("timeout_called", False, 0.0, {})

    def _detect_penalty(self, frame: np.ndarray) -> DetectionResult:
        """Detect penalty flag."""
        # Look for yellow flag animation
        return DetectionResult("penalty", False, 0.0, {})

    def _detect_turnover(self, frame: np.ndarray) -> DetectionResult:
        """Detect turnover event."""
        return DetectionResult("turnover", False, 0.0, {})

    # ──────────────────────────────────────────────────────────────────────────
    # CALL OF DUTY DETECTORS (placeholder implementations)
    # ──────────────────────────────────────────────────────────────────────────

    def _detect_kill(self, frame: np.ndarray) -> DetectionResult:
        """Detect kill in kill feed."""
        # OCR kill feed region for "You killed X" or "[Weapon] X"
        feed_text = self._ocr_region(frame, "kill_feed")
        if feed_text and "killed" in feed_text.lower():
            return DetectionResult("kill", True, 0.8, {"feed_text": feed_text})
        return DetectionResult("kill", False, 0.0, {})

    def _detect_death(self, frame: np.ndarray) -> DetectionResult:
        """Detect death (death cam, eliminated text)."""
        return DetectionResult("death", False, 0.0, {})

    def _detect_assist(self, frame: np.ndarray) -> DetectionResult:
        """Detect assist."""
        return DetectionResult("assist", False, 0.0, {})

    def _detect_streak(self, frame: np.ndarray) -> DetectionResult:
        """Detect streak counter change."""
        streak_text = self._ocr_region(frame, "streak")
        if streak_text:
            try:
                val = int(''.join(filter(str.isdigit, streak_text)))
                if val != self._prev_fields.get("streak"):
                    return DetectionResult("streak", True, 0.85, {"streak_count": val})
            except ValueError:
                pass
        return DetectionResult("streak", False, 0.0, {})

    def _detect_objective_capture(self, frame: np.ndarray) -> DetectionResult:
        """Detect objective capture (flag, point, bomb)."""
        return DetectionResult("objective_capture", False, 0.0, {})

    def _detect_objective_defend(self, frame: np.ndarray) -> DetectionResult:
        """Detect objective defend."""
        return DetectionResult("objective_defend", False, 0.0, {})

    def _detect_round_start(self, frame: np.ndarray) -> DetectionResult:
        """Detect round start."""
        return DetectionResult("round_start", False, 0.0, {})

    def _detect_round_end(self, frame: np.ndarray) -> DetectionResult:
        """Detect round end."""
        return DetectionResult("round_end", False, 0.0, {})

    def _detect_match_start(self, frame: np.ndarray) -> DetectionResult:
        """Detect match start."""
        return DetectionResult("match_start", False, 0.0, {})

    def _detect_match_end(self, frame: np.ndarray) -> DetectionResult:
        """Detect match end (final scoreboard)."""
        return DetectionResult("match_end", False, 0.0, {})

    # ──────────────────────────────────────────────────────────────────────────
    # OCR HELPER
    # ──────────────────────────────────────────────────────────────────────────

    def _refresh_ocr_cache(self, frame: np.ndarray) -> None:
        """Run EasyOCR once per frame and cache per-word bounding boxes."""
        frame_id = id(frame)
        if frame_id == self._last_frame_id:
            return

        # Skip blank frames quickly
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if float(np.std(gray)) < 8.0:
            self._last_frame_id = frame_id
            self._last_ocr_bboxes = []
            return

        try:
            self._last_ocr_bboxes = self._ocr_provider.read_text_with_bboxes(frame)
        except Exception as e:
            log.debug(f"Full-frame OCR failed: {e}")
            self._last_ocr_bboxes = []

        self._last_frame_id = frame_id

    def _ocr_region(self, frame: np.ndarray, region_name: str) -> Optional[str]:
        """Extract text from a named OCR region using the cached full-frame OCR."""
        if region_name not in self._ocr_regions:
            return None

        if id(frame) != self._last_frame_id:
            # Cache miss: refresh on demand
            self._refresh_ocr_cache(frame)

        h, w = frame.shape[:2]
        x_frac, y_frac, w_frac, h_frac = self._ocr_regions[region_name]

        x = int(x_frac * w)
        y = int(y_frac * h)
        rw = int(w_frac * w)
        rh = int(h_frac * h)

        # Select words whose bounding box center falls inside this region
        parts = []
        for (bbox, text, conf) in self._last_ocr_bboxes:
            if not text:
                continue
            # bbox is a list of four (x,y) corners in pixel coords
            try:
                cx = sum(p[0] for p in bbox) / 4.0
                cy = sum(p[1] for p in bbox) / 4.0
            except Exception:
                continue
            if x <= cx < x + rw and y <= cy < y + rh:
                parts.append((cy, text))

        if not parts:
            return None

        # Read top-to-bottom, left-to-right
        parts.sort(key=lambda t: (t[0], t[1]))
        return ", ".join(t[1] for t in parts)

    def _simple_ocr(self, thresh: np.ndarray, region_name: str) -> Optional[str]:
        """Simple template-based OCR fallback."""
        # This is a minimal placeholder - real impl would use template matching
        # or a lightweight OCR model
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # EVENT EMISSION
    # ──────────────────────────────────────────────────────────────────────────

    def _emit_session_start(self) -> None:
        self.bus.emit_raw(
            source_lobe=SourceLobe.OUTCOME,
            event_type="session_start",
            payload={
                "game_profile": self._profile.profile_id.value,
                "display_name": self._profile.display_name,
                "event_types": list(self._profile.event_types),
                "outcome_fields": list(self._profile.outcome_fields),
                "detection_method": self.config.detection_method,
                "confidence_threshold": self.config.confidence_threshold,
                "poll_interval_s": self.config.poll_interval_s,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    def _emit_outcome_event(self, result: DetectionResult) -> None:
        """Emit outcome event with profile-specific fields."""
        self.bus.emit_raw(
            source_lobe=SourceLobe.OUTCOME,
            event_type="outcome_event",
            payload={
                "event_name": result.event_name,
                "profile_id": self._profile.profile_id.value,
                "confidence": result.confidence,
                "fields": result.fields,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

        # Update tracking for cross-modal verification
        self._last_event = result.event_name
        if 'home_score' in result.fields:
            self._home_score = result.fields['home_score']
        if 'away_score' in result.fields:
            self._away_score = result.fields['away_score']

        # Call presence callback for fusion engine
        if self._presence_callback:
            try:
                self._presence_callback({
                    "lobe": "outcome",
                    "last_event": result.event_name,
                    "home_score": self._home_score,
                    "away_score": self._away_score,
                })
            except Exception:
                pass

        # Update prev_fields for change detection
        self._prev_fields.update(result.fields)

    def _emit_session_end(self) -> None:
        elapsed = max(time.time() - self._start_time, 1e-6)
        self.bus.emit_raw(
            source_lobe=SourceLobe.OUTCOME,
            event_type="session_end",
            payload={
                "detections": self._detections_count,
                "elapsed_s": round(elapsed, 2),
                "game_profile": self._profile.profile_id.value,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )


# ──────────────────────────────────────────────────────────────────────────────
# EXTERNAL TRIGGER INTERFACE (for testing / integration)
# ──────────────────────────────────────────────────────────────────────────────

class OutcomeTrigger:
    """
    External trigger interface for injecting outcome events
    without running the full detection loop (useful for testing).
    """

    def __init__(self, bus: RetinaEventBus, session_head_ns: int, game_profile: GameProfileId):
        self.bus = bus
        self.session_head_ns = session_head_ns
        self.profile = get_game_profile(game_profile)

    def emit(self, event_name: str, fields: dict[str, Any], confidence: float = 1.0) -> bool:
        """Emit an outcome event directly."""
        if event_name not in self.profile.event_types:
            log.warning(f"Unknown event {event_name} for profile {self.profile.profile_id}")
            return False

        self.bus.emit_raw(
            source_lobe=SourceLobe.OUTCOME,
            event_type="outcome_event",
            payload={
                "event_name": event_name,
                "profile_id": self.profile.profile_id.value,
                "confidence": confidence,
                "fields": fields,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )
        return True