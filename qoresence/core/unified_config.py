"""
Qoresence Unified Configuration — Phase 1 Foundation Stone

Single source of truth for all Qoresence lobes. All lobes default to OFF.
Eye-check mandatory. Never claims humanity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class SourceLobe(str, Enum):
    """Enumeration of all observation lobes."""
    STREAMER = "streamer"      # UVC / OBS Virtual Cam
    CONTROLLER = "controller"  # Local HID
    SCREEN = "screen"          # WGC / DXGI / mss
    OUTCOME = "outcome"        # Game-specific events
    VISUAL = "visual"          # VLM visual context


class GameProfileId(str, Enum):
    """First-class game profiles (equal citizens)."""
    NCAA_FOOTBALL_27 = "ncaa_football_27"
    CALL_OF_DUTY = "call_of_duty"


@dataclass(frozen=True)
class GameProfile:
    """Game-specific event vocabulary and semantics."""
    profile_id: GameProfileId
    display_name: str
    event_types: tuple[str, ...]  # canonical event type strings for this profile
    outcome_fields: tuple[str, ...]  # fields that appear in outcome events
    category: str  # "football" | "shooter" | "other"


# ──────────────────────────────────────────────────────────────────────────────
# FIRST-CLASS PROFILES: NCAA Football 27 and Call of Duty (equal citizens)
# ──────────────────────────────────────────────────────────────────────────────

NCAA_FOOTBALL_27_PROFILE = GameProfile(
    profile_id=GameProfileId.NCAA_FOOTBALL_27,
    display_name="NCAA College Football 27",
    event_types=(
        "snap",
        "down_advanced",
        "first_down",
        "score_changed",
        "playclock_reset",
        "quarter_changed",
        "possession_changed",
        "timeout_called",
        "penalty",
        "turnover",
    ),
    outcome_fields=(
        "home_score",
        "away_score",
        "quarter",
        "down",
        "yards_to_go",
        "possession",
        "play_clock",
        "game_clock",
        "field_position",
    ),
    category="football",
)

CALL_OF_DUTY_PROFILE = GameProfile(
    profile_id=GameProfileId.CALL_OF_DUTY,
    display_name="Call of Duty (Warzone / Multiplayer)",
    event_types=(
        "kill",
        "death",
        "assist",
        "streak",
        "objective_capture",
        "objective_defend",
        "round_start",
        "round_end",
        "match_start",
        "match_end",
    ),
    outcome_fields=(
        "kills",
        "deaths",
        "assists",
        "score",
        "streak_count",
        "team",
        "mode",
        "map",
    ),
    category="shooter",
)

# Registry of all known profiles (extensible)
GAME_PROFILE_REGISTRY: dict[GameProfileId, GameProfile] = {
    NCAA_FOOTBALL_27_PROFILE.profile_id: NCAA_FOOTBALL_27_PROFILE,
    CALL_OF_DUTY_PROFILE.profile_id: CALL_OF_DUTY_PROFILE,
}


def get_game_profile(profile_id: GameProfileId) -> GameProfile:
    """Retrieve a game profile by ID."""
    return GAME_PROFILE_REGISTRY[profile_id]


def register_game_profile(profile: GameProfile) -> None:
    """Register a new game profile (for extensibility)."""
    GAME_PROFILE_REGISTRY[profile.profile_id] = profile


# ──────────────────────────────────────────────────────────────────────────────
# LOBE-SPECIFIC CONFIGURATIONS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StreamerConfig:
    """Streamer lobe (UVC / OBS Virtual Cam / network stream) configuration."""
    enabled: bool = False
    device_index: int = 0
    device_name: Optional[str] = None
    url: Optional[str] = None  # network stream URL (rtmp://, http://, file, etc.)
    source_kind: str = "uvc_card"  # "uvc_card" | "obs_virtual" | "network" | "unknown"
    width: int = 1280
    height: int = 720
    fps_target: float = 15.0
    process_scale: float = 0.5
    backend: str = "auto"  # "auto" | "msmf" | "dshow"
    zones_enabled: bool = True
    eye_check_required: bool = True
    snapshot_path: Optional[str] = None
    ws_port: int = 8765
    enable_ws: bool = True
    presence_touch_file: Optional[str] = None
    presence_timeout_s: float = 5.0

    # Activity detection thresholds
    motion_high: float = 15.0
    motion_low: float = 3.0
    activity_hysteresis_s: float = 1.0

    # Emission intervals
    stats_every_s: float = 10.0
    heartbeat_every_s: float = 5.0


@dataclass(frozen=True)
class ControllerConfig:
    """Controller lobe (local HID) configuration."""
    enabled: bool = False
    device_vid: Optional[int] = None
    device_pid: Optional[int] = None
    device_path: Optional[str] = None
    poll_rate_hz: float = 1000.0
    buffer_size: int = 1000  # rolling buffer for causal correlation
    causal_parent_ns_enabled: bool = True


@dataclass(frozen=True)
class ScreenConfig:
    """Screen lobe (WGC / DXGI / mss) configuration."""
    enabled: bool = False
    capture_method: str = "wgc"  # "wgc" | "dxgi" | "mss"
    monitor_index: int = 0
    window_title_substring: Optional[str] = None
    fps_target: float = 60.0
    process_scale: float = 0.5
    cv_motion_enabled: bool = True
    ocr_enabled: bool = False
    ocr_regions: tuple[tuple[int, int, int, int], ...] = ()  # (x, y, w, h) tuples


@dataclass(frozen=True)
class OutcomeConfig:
    """Outcome lobe (game-specific events) configuration."""
    enabled: bool = False
    game_profile: GameProfileId = GameProfileId.NCAA_FOOTBALL_27
    detection_method: str = "ocr"  # "ocr" | "memory" | "hybrid"
    confidence_threshold: float = 0.7
    poll_interval_s: float = 0.5


@dataclass(frozen=True)
class VisualConfig:
    """Visual lobe (VLM) configuration."""
    enabled: bool = False
    model_endpoint: str = "https://integrate.api.nvidia.com/v1"
    model_name: str = "nvidia/nemotron-nano-12b-v2-vl"
    api_key: Optional[str] = None
    frame_sample_rate: int = 30  # analyze every N frames
    max_frame_dim: int = 640
    min_confidence: float = 0.6
    game_category: str = "football"  # "football" | "shooter" | "unknown"


@dataclass(frozen=True)
class GameDetectionConfig:
    """Game auto-detection configuration (VLM + OCR fusion)."""
    enabled: bool = False
    confidence_threshold: float = 0.65
    stability_count: int = 2
    poll_interval_s: float = 3.0
    learning_enabled: bool = False
    learning_path: Optional[str] = "game_detection_learning.jsonl"
    ocr_provider: str = "vlm"
    vision_model_dir: Optional[str] = "models"


@dataclass(frozen=True)
class FusionWeights:
    """Weights for the presence fusion engine (must sum to 1.0)."""
    streamer_presence_sync: float = 0.25
    controller_causal_density: float = 0.25
    screen_coupling_score: float = 0.20
    outcome_coherence: float = 0.15
    visual_confirmation: float = 0.15

    def validate(self) -> None:
        total = (
            self.streamer_presence_sync
            + self.controller_causal_density
            + self.screen_coupling_score
            + self.outcome_coherence
            + self.visual_confirmation
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Fusion weights must sum to 1.0, got {total}")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN UNIFIED CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RetinaUnifiedConfig:
    """
    Single source of truth for all Qoresence lobes.

    ALL LOBES DEFAULT TO FALSE — operator must explicitly enable each.
    Eye-check is mandatory for any video source.
    Never claims humanity, eligibility, or "anti-cheat".
    """

    # ── Session Identity (required) ──────────────────────────────────────────
    session_id: str = ""
    session_head_ns: int = 0
    device_id_hex: str = ""

    # ── Lobe Enablement (ALL DEFAULT FALSE) ─────────────────────────────────
    streamer: StreamerConfig = field(default_factory=StreamerConfig)
    controller: ControllerConfig = field(default_factory=ControllerConfig)
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    outcome: OutcomeConfig = field(default_factory=OutcomeConfig)
    visual: VisualConfig = field(default_factory=VisualConfig)
    game_detection: GameDetectionConfig = field(default_factory=GameDetectionConfig)

    # ── Fusion Engine ────────────────────────────────────────────────────────
    fusion_weights: FusionWeights = field(default_factory=FusionWeights)

    # ── Safety Contracts (NON-NEGOTIABLE) ───────────────────────────────────
    eye_check_required: bool = True
    never_claim_humanity: bool = True

    # ── Output Configuration ─────────────────────────────────────────────────
    jsonl_path: Optional[str] = None
    ws_host: str = "127.0.0.1"
    ws_port: int = 8765
    enable_ws: bool = True

    # ─────────────────────────────────────────────────────────────────────────
    # VALIDATION
    # ─────────────────────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """
        Validate the configuration. Returns list of errors (empty = valid).

        Enforces:
        - session_id is required
        - session_head_ns must be positive
        - device_id_hex must be 64 hex chars (32 bytes) if provided
        - fusion weights sum to 1.0
        - at least one lobe enabled (warning, not error)
        - eye_check_required is True
        - never_claim_humanity is True
        """
        errors = []

        # Required session identity
        if not self.session_id or not self.session_id.strip():
            errors.append("session_id is required (non-empty string)")

        if self.session_head_ns <= 0:
            errors.append("session_head_ns must be a positive integer (monotonic ns)")

        # Device ID format (if provided)
        if self.device_id_hex:
            if len(self.device_id_hex) != 64:
                errors.append("device_id_hex must be 64 hex characters (32 bytes)")
            try:
                bytes.fromhex(self.device_id_hex)
            except ValueError:
                errors.append("device_id_hex must be valid hexadecimal")

        # Fusion weights
        try:
            self.fusion_weights.validate()
        except ValueError as e:
            errors.append(str(e))

        # Safety contracts (hard requirements)
        if not self.eye_check_required:
            errors.append("eye_check_required must be True (non-negotiable)")

        if not self.never_claim_humanity:
            errors.append("never_claim_humanity must be True (non-negotiable)")

        # At least one lobe enabled (warning)
        any_enabled = (
            self.streamer.enabled
            or self.controller.enabled
            or self.screen.enabled
            or self.outcome.enabled
            or self.visual.enabled
        )
        if not any_enabled:
            # This is a warning, not an error — config is valid but useless
            pass

        # Streamer-specific validation
        if self.streamer.enabled:
            if self.streamer.eye_check_required is False:
                errors.append("streamer.eye_check_required must be True when streamer enabled")

        # Outcome-specific validation
        if self.outcome.enabled:
            if self.outcome.game_profile not in GAME_PROFILE_REGISTRY:
                errors.append(f"Unknown game profile: {self.outcome.game_profile}")

        return errors

    def is_valid(self) -> bool:
        """Return True if configuration is valid (no errors)."""
        return len(self.validate()) == 0

    # ─────────────────────────────────────────────────────────────────────────
    # FACTORY METHODS
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def create_session(
        cls,
        session_id: Optional[str] = None,
        device_id_hex: Optional[str] = None,
    ) -> "RetinaUnifiedConfig":
        """
        Create a new config with a minted session identity.

        If session_id not provided, generates one from timestamp.
        If device_id_hex not provided, leaves empty (operator must set).
        """
        now_ns = time.time_ns()
        sid = session_id or f"qoresence_{int(now_ns // 1_000_000)}"
        head_ns = now_ns

        return cls(
            session_id=sid,
            session_head_ns=head_ns,
            device_id_hex=device_id_hex or "",
        )

    @classmethod
    def from_env(cls) -> "RetinaUnifiedConfig":
        """
        Create config from environment variables (for CLI/daemon usage).

        Expected env vars:
        - QORESENCE_SESSION_ID
        - QORESENCE_DEVICE_ID_HEX
        - QORESENCE_STREAMER_ENABLED (1/0)
        - QORESENCE_STREAMER_DEVICE_INDEX
        - QORESENCE_CONTROLLER_ENABLED (1/0)
        - QORESENCE_SCREEN_ENABLED (1/0)
        - QORESENCE_OUTCOME_ENABLED (1/0)
        - QORESENCE_OUTCOME_GAME_PROFILE
        - QORESENCE_VISUAL_ENABLED (1/0)
        - QORESENCE_VISUAL_API_KEY
        - QORESENCE_JSONL_PATH
        """
        import os

        def _bool(key: str, default: bool = False) -> bool:
            val = os.environ.get(key, "").strip().lower()
            return val in ("1", "true", "yes", "on") if val else default

        def _int(key: str, default: int = 0) -> int:
            val = os.environ.get(key, "").strip()
            return int(val) if val else default

        def _float(key: str, default: float = 0.0) -> float:
            val = os.environ.get(key, "").strip()
            return float(val) if val else default

        def _str(key: str, default: str = "") -> str:
            return os.environ.get(key, default)

        return cls(
            session_id=_str("QORESENCE_SESSION_ID"),
            session_head_ns=_int("QORESENCE_SESSION_HEAD_NS", 0),
            device_id_hex=_str("QORESENCE_DEVICE_ID_HEX"),
            streamer=StreamerConfig(
                enabled=_bool("QORESENCE_STREAMER_ENABLED"),
                device_index=_int("QORESENCE_STREAMER_DEVICE_INDEX", 0),
                device_name=_str("QORESENCE_STREAMER_DEVICE_NAME"),
                source_kind=_str("QORESENCE_STREAMER_SOURCE_KIND", "uvc_card"),
                fps_target=_float("QORESENCE_STREAMER_FPS", 15.0),
                ws_port=_int("QORESENCE_STREAMER_WS_PORT", 8765),
                enable_ws=_bool("QORESENCE_STREAMER_WS_ENABLED", True),
                presence_touch_file=_str("QORESENCE_STREAMER_PRESENCE_TOUCH"),
                presence_timeout_s=_float("QORESENCE_STREAMER_PRESENCE_TIMEOUT", 5.0),
            ),
            controller=ControllerConfig(
                enabled=_bool("QORESENCE_CONTROLLER_ENABLED"),
                device_vid=_int("QORESENCE_CONTROLLER_VID") or None,
                device_pid=_int("QORESENCE_CONTROLLER_PID") or None,
                device_path=_str("QORESENCE_CONTROLLER_PATH") or None,
            ),
            screen=ScreenConfig(
                enabled=_bool("QORESENCE_SCREEN_ENABLED"),
                capture_method=_str("QORESENCE_SCREEN_METHOD", "wgc"),
                monitor_index=_int("QORESENCE_SCREEN_MONITOR", 0),
            ),
            outcome=OutcomeConfig(
                enabled=_bool("QORESENCE_OUTCOME_ENABLED"),
                game_profile=GameProfileId(_str("QORESENCE_OUTCOME_PROFILE", "ncaa_football_27")),
                confidence_threshold=_float("QORESENCE_OUTCOME_CONFIDENCE", 0.7),
            ),
            visual=VisualConfig(
                enabled=_bool("QORESENCE_VISUAL_ENABLED"),
                api_key=_str("QORESENCE_VISUAL_API_KEY") or None,
                frame_sample_rate=_int("QORESENCE_VISUAL_SAMPLE_RATE", 30),
                game_category=_str("QORESENCE_VISUAL_CATEGORY", "football"),
            ),
            game_detection=GameDetectionConfig(
                enabled=_bool("QORESENCE_GAME_DETECT_ENABLED"),
                confidence_threshold=_float("QORESENCE_GAME_DETECT_THRESHOLD", 0.65),
                poll_interval_s=_float("QORESENCE_GAME_DETECT_POLL", 3.0),
                learning_enabled=_bool("QORESENCE_GAME_DETECT_LEARNING"),
            ),
            jsonl_path=_str("QORESENCE_JSONL_PATH") or None,
            ws_host=_str("QORESENCE_WS_HOST", "127.0.0.1"),
            ws_port=_int("QORESENCE_WS_PORT", 8765),
            enable_ws=_bool("QORESENCE_WS_ENABLED", True),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # GAME PROFILE ACCESSORS
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def active_game_profile(self) -> GameProfile:
        """Get the active game profile for the outcome lobe."""
        return get_game_profile(self.outcome.game_profile)

    def get_event_types_for_profile(self) -> tuple[str, ...]:
        """Get the canonical event types for the active game profile."""
        return self.active_game_profile.event_types

    def get_outcome_fields_for_profile(self) -> tuple[str, ...]:
        """Get the outcome fields for the active game profile."""
        return self.active_game_profile.outcome_fields