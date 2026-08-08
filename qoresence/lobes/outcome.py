"""
Qoresence Outcome Lobe — VLM-driven

Game-specific event detection and emission, now driven by the structured
VisualContext produced by the VLM visual oracle. This matches QorTroller's
Retina Visual Oracle pattern: the VLM reads the scoreboard/HUD once, and the
outcome lobe derives events from field changes rather than running its own
heavy local OCR loop.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from qoresence.core import (
    EventType,
    GameProfile,
    GameProfileId,
    OutcomeConfig,
    RetinaEventBus,
    SourceLobe,
    clock_ns,
    get_game_profile,
    normalize_game_profile,
)
from qoresence.vision.visual_context import (
    GameCategory,
    GameState,
    VisualContext,
)

log = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """Result of a single detector check."""

    event_name: str
    detected: bool
    confidence: float
    fields: dict[str, Any]


# Legacy OCR region constants kept for backward-compat in tests / diagnostics
NCAA_OCR_REGIONS = {
    "scoreboard": (0.15, 0.02, 0.7, 0.08),
    "down_distance": (0.05, 0.10, 0.25, 0.06),
    "possession": (0.75, 0.02, 0.2, 0.04),
    "play_clock": (0.45, 0.08, 0.1, 0.04),
    "game_clock": (0.85, 0.02, 0.1, 0.04),
    "quarter": (0.05, 0.02, 0.1, 0.04),
    "yard_line": (0.3, 0.90, 0.4, 0.06),
}

COD_OCR_REGIONS = {
    "kill_feed": (0.7, 0.15, 0.25, 0.6),
    "score": (0.05, 0.02, 0.2, 0.05),
    "health": (0.05, 0.90, 0.2, 0.05),
    "ammo": (0.75, 0.90, 0.2, 0.05),
    "mini_map": (0.75, 0.02, 0.2, 0.15),
    "streak": (0.35, 0.02, 0.3, 0.05),
}


class OutcomeRuntime:
    """
    Game-specific outcome event detector.

    Subscribes to the event bus and derives outcome events from:
    - game_detected (sets active profile and emits session_start)
    - visual_context (compares VLM-extracted scoreboard/HUD fields)

    No longer polls frames or runs local EasyOCR, which was starving the
    GameAutoDetector's VLM pipeline.
    """

    def __init__(
        self,
        config: OutcomeConfig,
        bus: RetinaEventBus,
        session_head_ns: int,
        frame_provider: Callable[[], Any | None] | None = None,
    ):
        self.config = config
        self.bus = bus
        self.session_head_ns = session_head_ns

        # Optional frame provider is ignored in the VLM-driven path but kept
        # for interface compatibility.
        self._frame_provider = frame_provider

        # Profile
        self._profile: GameProfile = get_game_profile(config.game_profile)

        # State
        self._running = False
        self._unsubscribe: Callable[[], None] | None = None
        self._active = False
        self._detections_count = 0
        self._start_time = 0.0

        # Previous visual context for change detection
        self._prev_context: VisualContext | None = None

        # Cached football state
        self._home_score: int | None = None
        self._away_score: int | None = None
        self._quarter: int | None = None
        self._down: int | None = None
        self._yards_to_go: int | None = None
        self._possession: str | None = None
        self._field_position: str | None = None
        self._play_clock: int | None = None
        self._game_clock_seconds: int | None = None
        self._in_red_zone: bool = False
        self._two_min_warn_emitted: set[int] = set()  # quarters where 2-min warning fired

        # Cached shooter state
        self._shooter_score: int | None = None
        self._health: int | None = None
        self._ammo: int | None = None
        self._enemies_visible: int = 0

        # Presence callback (for fusion engine)
        self._presence_callback: callable | None = None

        # Confidence threshold
        self._confidence_threshold = config.confidence_threshold

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start the outcome lobe by subscribing to visual context events."""
        if self._running:
            log.warning("OutcomeRuntime already running")
            return True

        self._running = True
        self._start_time = time.time()
        # Active immediately for the configured profile. Waiting only for
        # GAME_DETECTED left score_changed silent under --play (no game_detect),
        # so ClutchBot never saw clutch moments despite live OCR scores.
        self._active = True
        self._unsubscribe = self.bus.subscribe(self._on_event)

        log.info(
            f"Outcome lobe started: profile={self._profile.profile_id.value}, method=vlm_context, active={self._active}"
        )
        return True

    def stop(self) -> None:
        """Stop the outcome lobe and unsubscribe from bus events."""
        self._running = False
        if self._unsubscribe:
            try:
                self._unsubscribe()
            except Exception as e:
                log.debug(f"Outcome unsubscribe failed: {e}")
            self._unsubscribe = None
        self._emit_session_end()
        log.info("Outcome lobe stopped")

    def is_running(self) -> bool:
        return self._running

    def set_frame_provider(self, provider: Callable[[], Any | None]) -> None:
        """Set frame provider callback (kept for compatibility; unused)."""
        self._frame_provider = provider

    def set_presence_callback(self, callback: callable) -> None:
        """Set callback for presence status updates (for fusion engine)."""
        self._presence_callback = callback

    def set_game_profile(self, profile_id: GameProfileId | str) -> None:
        """Switch the active game profile and reset state."""
        canonical = normalize_game_profile(profile_id)
        if self._profile.profile_id == canonical:
            return

        self.config = replace(self.config, game_profile=canonical)
        self._profile = get_game_profile(canonical)
        self._reset_state()
        log.info(f"Outcome lobe switched to profile: {canonical.value}")

    def get_last_state(self) -> dict:
        """Get last outcome state for cross-modal verification."""
        return {
            "home_score": self._home_score,
            "away_score": self._away_score,
            "quarter": self._quarter,
            "down": self._down,
            "yards_to_go": self._yards_to_go,
            "possession": self._possession,
            "shooter_score": self._shooter_score,
            "health": self._health,
            "ammo": self._ammo,
            "enemies_visible": self._enemies_visible,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # EVENT HANDLERS
    # ──────────────────────────────────────────────────────────────────────────

    def _on_event(self, event: Any) -> None:
        """Dispatch incoming bus events."""
        if not self._running:
            return

        if event.type == EventType.GAME_DETECTED:
            self._on_game_detected(event)
        elif event.type == EventType.VISUAL_CONTEXT:
            self._on_visual_context(event)

    def _on_game_detected(self, event: Any) -> None:
        """Handle a new stable game detection."""
        raw_id = event.payload.get("profile_id")
        if not raw_id:
            log.warning("Outcome: game_detected payload missing profile_id")
            return

        try:
            profile_id = normalize_game_profile(raw_id)
        except ValueError:
            log.warning(f"Outcome: unknown game profile: {raw_id}")
            return

        if self._profile.profile_id != profile_id:
            self.set_game_profile(profile_id)

        self._active = True
        self._reset_state()
        self._emit_session_start()

    def _on_visual_context(self, event: Any) -> None:
        """Process a structured visual context from the VLM."""
        if not self._active:
            return

        try:
            ctx = VisualContext.from_dict(event.payload)
        except Exception as e:
            log.warning(f"Outcome: failed to parse visual context: {e}")
            return

        if ctx.confidence < self._confidence_threshold:
            return

        # Ignore pure menu/lobby/loading screens for outcome events
        if ctx.game_state in {
            GameState.MENU,
            GameState.LOBBY,
            GameState.LOADING,
            GameState.CUTSCENE,
        }:
            return

        if self._profile.profile_id == GameProfileId.NCAA_FOOTBALL_27:
            if ctx.game_category == GameCategory.FOOTBALL:
                self._process_football(ctx)
        elif self._profile.profile_id == GameProfileId.CALL_OF_DUTY:
            if ctx.game_category == GameCategory.SHOOTER:
                self._process_shooter(ctx)

    # ──────────────────────────────────────────────────────────────────────────
    # FOOTBALL PROCESSING
    # ──────────────────────────────────────────────────────────────────────────

    def _process_football(self, ctx: VisualContext) -> None:
        """Derive NCAA football outcome events from VisualContext changes."""
        if self._prev_context is None:
            self._sync_football_state(ctx)
            return

        # Score change — reject flaky OCR (e.g. 17-17 → 17-2 single-frame glitch)
        if ctx.home_score != self._home_score or ctx.away_score != self._away_score:
            fields: dict[str, Any] = {}
            if ctx.home_score is not None and ctx.home_score != self._home_score:
                if self._score_change_ok(self._home_score, ctx.home_score):
                    fields["home_score"] = ctx.home_score
                    fields["prev_home_score"] = self._home_score
                    self._home_score = ctx.home_score
                else:
                    log.debug(
                        "outcome reject home_score OCR %s → %s",
                        self._home_score,
                        ctx.home_score,
                    )
            if ctx.away_score is not None and ctx.away_score != self._away_score:
                if self._score_change_ok(self._away_score, ctx.away_score):
                    fields["away_score"] = ctx.away_score
                    fields["prev_away_score"] = self._away_score
                    self._away_score = ctx.away_score
                else:
                    log.debug(
                        "outcome reject away_score OCR %s → %s",
                        self._away_score,
                        ctx.away_score,
                    )
            if fields:
                self._emit_outcome_event("score_changed", fields, ctx.confidence)
                # Infer scoring type from delta
                self._infer_score_type(fields, ctx)

        # Quarter change
        if ctx.quarter is not None and ctx.quarter != self._quarter:
            self._emit_outcome_event(
                "quarter_changed",
                {"quarter": ctx.quarter, "prev_quarter": self._quarter},
                ctx.confidence,
            )
            self._quarter = ctx.quarter

        # First down: down == 1 and previous down was not 1 (and not a fresh quarter start)
        if ctx.down is not None and ctx.down == 1 and self._down is not None and self._down != 1:
            self._emit_outcome_event(
                "first_down",
                {
                    "down": ctx.down,
                    "yards_to_go": ctx.yards_to_go,
                    "possession": ctx.possession,
                },
                ctx.confidence,
            )

        # Down advanced (down changed and not just a first-down emission)
        if ctx.down is not None and ctx.down != self._down:
            self._emit_outcome_event(
                "down_advanced",
                {"down": ctx.down, "prev_down": self._down, "yards_to_go": ctx.yards_to_go},
                ctx.confidence,
            )

        # Possession change
        if (
            ctx.possession is not None
            and ctx.possession != self._possession
            and self._possession is not None
        ):
            # Turnover heuristic: possession flipped while in opponent territory
            # and no score change. Use field position to detect a sudden reversal.
            prev_yard = self._field_position_to_yard_line(self._field_position)
            cur_yard = self._field_position_to_yard_line(ctx.field_position)
            in_opp_territory = prev_yard is not None and prev_yard >= 60
            moved_back_to_own = cur_yard is not None and cur_yard <= 40

            if in_opp_territory and moved_back_to_own:
                self._emit_outcome_event(
                    "turnover",
                    {
                        "possession": ctx.possession,
                        "prev_possession": self._possession,
                        "field_position": ctx.field_position,
                        "prev_field_position": self._field_position,
                    },
                    ctx.confidence,
                )
            else:
                self._emit_outcome_event(
                    "possession_changed",
                    {"possession": ctx.possession, "prev_possession": self._possession},
                    ctx.confidence,
                )

        # Play clock reset (play_clock jumps up after being low)
        if (
            ctx.play_clock is not None
            and self._play_clock is not None
            and ctx.play_clock > self._play_clock
            and self._play_clock <= 5
        ):
            self._emit_outcome_event(
                "playclock_reset",
                {"play_clock": ctx.play_clock, "prev_play_clock": self._play_clock},
                ctx.confidence,
            )

        # Red zone entry: ball crosses into opponent's 20-yard line
        cur_yard = self._field_position_to_yard_line(ctx.field_position)
        if cur_yard is not None and cur_yard >= 80 and not self._in_red_zone:
            self._in_red_zone = True
            self._emit_outcome_event(
                "red_zone_entry",
                {"field_position": ctx.field_position, "yard_line": cur_yard},
                ctx.confidence,
            )
        elif cur_yard is not None and cur_yard < 80:
            self._in_red_zone = False

        # Two-minute warning: game clock crosses below 120s (2:00) in Q2/Q4
        if (
            ctx.clock_seconds is not None
            and ctx.clock_seconds <= 120
            and ctx.quarter is not None
            and ctx.quarter in (2, 4)
            and ctx.quarter not in self._two_min_warn_emitted
        ):
            self._two_min_warn_emitted.add(ctx.quarter)
            self._emit_outcome_event(
                "two_minute_warning",
                {"quarter": ctx.quarter, "clock_seconds": ctx.clock_seconds},
                ctx.confidence,
            )

        # Sync state after change detection so we don't double-emit
        self._sync_football_state(ctx)

    @staticmethod
    def _score_change_ok(prev: int | None, new: int | None) -> bool:
        """Gate OCR score flips — reject classic misreads (17→2) without consensus path.

        Stabilizer upstream should already filter; this is a second belt for outcome events.
        """
        if new is None:
            return False
        if prev is None:
            return 0 <= int(new) <= 99
        try:
            p, n = int(prev), int(new)
        except Exception:
            return False
        if not (0 <= n <= 99):
            return False
        if p == n:
            return True
        d = n - p
        # Large drops are almost always OCR (17→2, 21→1)
        if d <= -7:
            return False
        # Any decrease is suspicious for football (scores only go up in-game)
        if d < 0:
            return False
        # Unrealistically large single-play jump
        if d > 14:
            return False
        return True

    @staticmethod
    def _infer_score_delta(prev: int | None, new: int | None) -> int:
        """Return the score delta (0 if either is None)."""
        if prev is None or new is None:
            return 0
        try:
            return max(0, int(new) - int(prev))
        except Exception:
            return 0

    def _infer_score_type(self, fields: dict[str, Any], ctx: VisualContext) -> None:
        """Infer touchdown / field_goal / safety / two_point from score delta.

        Football scoring:
          6 = touchdown (no PAT)
          7 = touchdown + PAT (most common)
          8 = touchdown + 2-point conversion
          3 = field goal
          2 = safety or 2-point conversion (context-dependent)
          1 = extra point only (rare, usually part of 7)
        """
        for side, prev_key, new_key in (
            ("home", "prev_home_score", "home_score"),
            ("away", "prev_away_score", "away_score"),
        ):
            if prev_key not in fields or new_key not in fields:
                continue
            delta = self._infer_score_delta(fields.get(prev_key), fields.get(new_key))
            if delta <= 0:
                continue
            if delta == 8:
                self._emit_outcome_event(
                    "touchdown",
                    {"side": side, "delta": delta, "pat_type": "two_point"},
                    ctx.confidence,
                )
                self._emit_outcome_event(
                    "two_point_conversion",
                    {"side": side, "delta": delta},
                    ctx.confidence,
                )
            elif delta == 7:
                self._emit_outcome_event(
                    "touchdown",
                    {"side": side, "delta": delta, "pat_type": "kick"},
                    ctx.confidence,
                )
            elif delta == 6:
                self._emit_outcome_event(
                    "touchdown",
                    {"side": side, "delta": delta, "pat_type": "missed"},
                    ctx.confidence,
                )
            elif delta == 3:
                self._emit_outcome_event(
                    "field_goal",
                    {"side": side, "delta": delta},
                    ctx.confidence,
                )
            elif delta == 2:
                # Safety vs 2-point: if score just changed on this side, likely 2PC
                # after a TD. Otherwise safety. We emit safety as the default.
                self._emit_outcome_event(
                    "safety",
                    {"side": side, "delta": delta},
                    ctx.confidence,
                )

    def _sync_football_state(self, ctx: VisualContext) -> None:
        """Update cached football state (scores only when OCR change is plausible)."""
        if ctx.home_score is not None and self._score_change_ok(self._home_score, ctx.home_score):
            self._home_score = ctx.home_score
        if ctx.away_score is not None and self._score_change_ok(self._away_score, ctx.away_score):
            self._away_score = ctx.away_score
        self._quarter = ctx.quarter if ctx.quarter is not None else self._quarter
        self._down = ctx.down if ctx.down is not None else self._down
        if ctx.yards_to_go is not None:
            self._yards_to_go = ctx.yards_to_go
        self._possession = ctx.possession
        self._field_position = ctx.field_position
        self._play_clock = ctx.play_clock
        if ctx.clock_seconds is not None:
            self._game_clock_seconds = ctx.clock_seconds
        self._prev_context = ctx

    @staticmethod
    def _field_position_to_yard_line(field_position: str | None) -> int | None:
        """Map a field position string to a 0-100 yard line.

        0 = own goal line, 50 = midfield, 100 = opponent goal line.
        Examples: "opp 10" -> 90, "own 25" -> 25, "opponent 15" -> 85.
        """
        if not field_position:
            return None
        pos = field_position.lower().strip()
        match = re.search(r"opp(?:onent)?\s*(\d+)", pos)
        if match:
            yard = int(match.group(1))
            return min(100, 100 - yard)
        match = re.search(r"own\s*(\d+)", pos)
        if match:
            return min(100, int(match.group(1)))
        match = re.search(r"(\d+)", pos)
        if match:
            # Ambiguous numeric-only: assume distance from own goal
            return min(100, int(match.group(1)))
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # SHOOTER PROCESSING
    # ──────────────────────────────────────────────────────────────────────────

    def _process_shooter(self, ctx: VisualContext) -> None:
        """Derive Call of Duty outcome events from VisualContext changes."""
        if self._prev_context is None:
            self._sync_shooter_state(ctx)
            return

        # Score change
        if ctx.score is not None and ctx.score != self._shooter_score:
            self._emit_outcome_event(
                "kill",
                {"score": ctx.score, "prev_score": self._shooter_score},
                ctx.confidence,
            )
            self._shooter_score = ctx.score

        # Health drop (tentative death indicator)
        if (
            ctx.health is not None
            and self._health is not None
            and ctx.health < self._health
            and ctx.health == 0
        ):
            self._emit_outcome_event("death", {"health": ctx.health}, ctx.confidence)

        self._sync_shooter_state(ctx)

    def _sync_shooter_state(self, ctx: VisualContext) -> None:
        """Update cached shooter state."""
        self._shooter_score = ctx.score
        self._health = ctx.health
        self._ammo = ctx.ammo
        self._enemies_visible = ctx.enemies_visible
        self._prev_context = ctx

    # ──────────────────────────────────────────────────────────────────────────
    # STATE HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _reset_state(self) -> None:
        self._prev_context = None
        self._home_score = None
        self._away_score = None
        self._quarter = None
        self._down = None
        self._yards_to_go = None
        self._possession = None
        self._field_position = None
        self._play_clock = None
        self._game_clock_seconds = None
        self._in_red_zone = False
        self._two_min_warn_emitted.clear()
        self._shooter_score = None
        self._health = None
        self._ammo = None
        self._enemies_visible = 0

    # ──────────────────────────────────────────────────────────────────────────
    # EMITTERS
    # ──────────────────────────────────────────────────────────────────────────

    def _emit_outcome_event(
        self, event_name: str, fields: dict[str, Any], confidence: float
    ) -> None:
        """Emit a single outcome event."""
        if event_name not in self._profile.event_types:
            log.debug(f"Outcome event {event_name} not in profile; skipping")
            return

        self.bus.emit_raw(
            source_lobe=SourceLobe.OUTCOME,
            event_type=EventType.OUTCOME_EVENT,
            payload={
                "event_name": event_name,
                "profile_id": self._profile.profile_id.value,
                "confidence": confidence,
                "fields": fields,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )
        self._detections_count += 1

    def _emit_session_start(self) -> None:
        self.bus.emit_raw(
            source_lobe=SourceLobe.OUTCOME,
            event_type=EventType.SESSION_START,
            payload={"game_profile": self._profile.profile_id.value},
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )
        self._detections_count += 1

    def _emit_session_end(self) -> None:
        elapsed = max(time.time() - self._start_time, 1e-6)
        self.bus.emit_raw(
            source_lobe=SourceLobe.OUTCOME,
            event_type=EventType.SESSION_END,
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
            event_type=EventType.OUTCOME_EVENT,
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
