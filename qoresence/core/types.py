"""
Qoresence Core Types — Phase 2

Shared event types, enums, and base classes for all lobes.
All events MUST carry: session_id, clock_ns, source_lobe
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import time


class SourceLobe(str, Enum):
    """Enumeration of all observation lobes."""
    STREAMER = "streamer"      # UVC / OBS Virtual Cam
    CONTROLLER = "controller"  # Local HID
    SCREEN = "screen"          # WGC / DXGI / mss
    OUTCOME = "outcome"        # Game-specific events
    VISUAL = "visual"          # VLM visual context


class EventType(str, Enum):
    """Standard event types across lobes."""
    # Streamer lobe
    ACTIVITY = "activity"
    FRAME_STATS = "frame_stats"
    ZONE = "zone"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    HEARTBEAT = "heartbeat"
    SOURCE_SECONDARY_FAILED = "source_secondary_failed"

    # Controller lobe
    CONTROLLER_EVENT = "controller_event"
    TRIGGER_ONSET = "trigger_onset"
    STICK_MOTION = "stick_motion"
    TREMOR_SAMPLE = "tremor_sample"

    # Screen lobe
    CV_MOTION = "cv_motion"
    OCR_HUD = "ocr_hud"
    COUPLING_SCORE = "coupling_score"

    # Outcome lobe
    OUTCOME_EVENT = "outcome_event"

    # Visual lobe
    VISUAL_CONTEXT = "visual_context"
    CROSS_MODAL_VERDICT = "cross_modal_verdict"

    # Fusion
    PRESENCE_REPORT = "presence_report"

    # Validation / anomalies
    ANOMALY = "anomaly"


# ──────────────────────────────────────────────────────────────────────────────
# BASE EVENT STRUCTURE
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_EVENT_FIELDS = ("session_id", "clock_ns", "source_lobe", "type", "payload")


@dataclass
class BaseEvent:
    """
    Base event that all lobe events must extend.

    NON-NEGOTIABLE: Every event carries session_id + clock_ns + source_lobe.
    """
    session_id: str
    clock_ns: int
    source_lobe: SourceLobe
    type: EventType
    payload: dict[str, Any]
    session_head_ns: Optional[int] = None
    ts_ns: Optional[int] = None  # wall-clock timestamp

    def __post_init__(self):
        if self.ts_ns is None:
            self.ts_ns = time.time_ns()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSONL/WebSocket."""
        d = {
            "session_id": self.session_id,
            "clock_ns": self.clock_ns,
            "source_lobe": self.source_lobe.value,
            "type": self.type.value,
            "payload": self.payload,
        }
        if self.session_head_ns is not None:
            d["session_head_ns"] = self.session_head_ns
        if self.ts_ns is not None:
            d["ts_ns"] = self.ts_ns
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseEvent":
        """Deserialize from dict."""
        return cls(
            session_id=data["session_id"],
            clock_ns=data["clock_ns"],
            source_lobe=SourceLobe(data["source_lobe"]),
            type=EventType(data["type"]),
            payload=data["payload"],
            session_head_ns=data.get("session_head_ns"),
            ts_ns=data.get("ts_ns"),
        )

    def validate(self) -> list[str]:
        """Validate required fields. Returns list of errors (empty = valid)."""
        errors = []
        if not self.session_id:
            errors.append("session_id is required")
        if self.clock_ns <= 0:
            errors.append("clock_ns must be positive")
        if not isinstance(self.source_lobe, SourceLobe):
            errors.append("source_lobe must be a SourceLobe enum")
        if not isinstance(self.type, EventType):
            errors.append("type must be an EventType enum")
        if not isinstance(self.payload, dict):
            errors.append("payload must be a dict")
        return errors


# ──────────────────────────────────────────────────────────────────────────────
# LOBE-SPECIFIC EVENT PAYLOADS (TypedDict for clarity)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class StreamerPayload:
    """Streamer lobe event payloads."""
    # activity event
    level: Optional[str] = None          # "idle" | "low" | "high"
    motion: Optional[float] = None
    mean_luma: Optional[float] = None
    presence_sync_ok: Optional[bool] = None
    last_controller_s_ago: Optional[float] = None

    # frame_stats event
    n: Optional[int] = None
    fps_meas: Optional[float] = None

    # zone event
    zone_id: Optional[str] = None
    state: Optional[str] = None          # "quiet" | "active"
    delta: Optional[float] = None
    luma: Optional[float] = None


@dataclass
class ControllerPayload:
    """Controller lobe event payloads."""
    # Generic controller event
    button: Optional[str] = None
    value: Optional[float] = None
    causal_parent_ns: Optional[int] = None  # links to screen/outcome event

    # Trigger onset
    trigger: Optional[str] = None           # "L2" | "R2"
    amplitude: Optional[float] = None
    device_ts_ms: Optional[int] = None

    # Stick motion
    stick: Optional[str] = None             # "left" | "right"
    x: Optional[float] = None
    y: Optional[float] = None


@dataclass
class ScreenPayload:
    """Screen lobe event payloads."""
    coupling_score: Optional[float] = None
    negative_control: Optional[float] = None
    decoupled_energy: Optional[float] = None
    best_lag_ms: Optional[float] = None
    ocr_region: Optional[str] = None
    ocr_text: Optional[str] = None


@dataclass
class OutcomePayload:
    """Outcome lobe event payloads (game-profile specific)."""
    event_name: str                          # e.g., "snap", "kill", "down_advanced"
    profile_id: str                          # "ncaa_football_27" | "call_of_duty"
    confidence: float
    fields: dict[str, Any]                   # profile-specific fields


@dataclass
class VisualPayload:
    """Visual lobe event payloads."""
    game_state: Optional[str] = None
    game_title: Optional[str] = None
    game_category: Optional[str] = None      # "football" | "shooter"
    confidence: Optional[float] = None
    frame_hash: Optional[str] = None
    # Game-specific fields (football)
    football_home_score: Optional[int] = None
    football_away_score: Optional[int] = None
    football_quarter: Optional[int] = None
    football_down: Optional[int] = None
    football_yards_to_go: Optional[int] = None
    football_possession: Optional[str] = None
    football_clock_seconds: Optional[int] = None
    football_play_clock: Optional[int] = None
    # Game-specific fields (shooter)
    health: Optional[float] = None
    ammo: Optional[int] = None
    kills: Optional[int] = None
    deaths: Optional[int] = None


@dataclass
class FusionPayload:
    """Fusion engine event payloads."""
    presence_sync_ok: bool
    weighted_verdict: str
    lobe_contributions: dict[str, float]
    anomalies: list[dict[str, Any]]


# ──────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def make_event(
    session_id: str,
    clock_ns: int,
    source_lobe: SourceLobe,
    event_type: EventType,
    payload: dict[str, Any],
    session_head_ns: Optional[int] = None,
) -> BaseEvent:
    """Factory for creating validated events."""
    event = BaseEvent(
        session_id=session_id,
        clock_ns=clock_ns,
        source_lobe=source_lobe,
        type=event_type,
        payload=payload,
        session_head_ns=session_head_ns,
    )
    errors = event.validate()
    if errors:
        raise ValueError(f"Invalid event: {errors}")
    return event


def clock_ns() -> int:
    """Monotonic clock for cross-lobe correlation."""
    return time.monotonic_ns()