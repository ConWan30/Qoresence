"""
Qoresence Core Types — Phase 2

Shared event types, enums, and base classes for all lobes.
All events MUST carry: session_id, clock_ns, source_lobe
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SourceLobe(StrEnum):
    """Enumeration of all event sources (lobes and agents)."""

    STREAMER = "streamer"  # UVC / OBS Virtual Cam
    CONTROLLER = "controller"  # Local HID
    SCREEN = "screen"  # WGC / DXGI / mss
    OUTCOME = "outcome"  # Game-specific events
    VISUAL = "visual"  # VLM visual context
    FUSION = "fusion"  # Cross-lobe fusion / game detection
    AGENT = "agent"  # Autonomous agents (ClutchBot, etc.)
    STEM = "stem"  # Retina Stem conductor / audio / record


class EventType(StrEnum):
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

    # Game detection / optical title-presence
    GAME_DETECTED = "game_detected"
    TITLE_PRESENCE = "title_presence"

    # Fusion
    PRESENCE_REPORT = "presence_report"

    # Retina Stem (situation-directed program; not OBS scenes)
    STEM_PROGRAM = "stem_program"
    STEM_AUDIO = "stem_audio"
    STEM_RECORD = "stem_record"

    # Agent actions
    AGENT_ACTION = "agent_action"
    EVIDENCE_CHAIN = "evidence_chain"
    ROUTER_DECISION = "router_decision"

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
    session_head_ns: int | None = None
    ts_ns: int | None = None  # wall-clock timestamp

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
    def from_dict(cls, data: dict[str, Any]) -> BaseEvent:
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
            raw = getattr(self.source_lobe, "value", self.source_lobe)
            try:
                self.source_lobe = SourceLobe(str(raw))
            except (TypeError, ValueError):
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
    level: str | None = None  # "idle" | "low" | "high"
    motion: float | None = None
    mean_luma: float | None = None
    presence_sync_ok: bool | None = None
    last_controller_s_ago: float | None = None

    # frame_stats event
    n: int | None = None
    fps_meas: float | None = None

    # zone event
    zone_id: str | None = None
    state: str | None = None  # "quiet" | "active"
    delta: float | None = None
    luma: float | None = None


@dataclass
class ControllerPayload:
    """Controller lobe event payloads."""

    # Generic controller event
    button: str | None = None
    value: float | None = None
    causal_parent_ns: int | None = None  # links to screen/outcome event

    # Trigger onset
    trigger: str | None = None  # "L2" | "R2"
    amplitude: float | None = None
    device_ts_ms: int | None = None

    # Stick motion
    stick: str | None = None  # "left" | "right"
    x: float | None = None
    y: float | None = None


@dataclass
class ScreenPayload:
    """Screen lobe event payloads."""

    coupling_score: float | None = None
    negative_control: float | None = None
    decoupled_energy: float | None = None
    best_lag_ms: float | None = None
    ocr_region: str | None = None
    ocr_text: str | None = None


@dataclass
class OutcomePayload:
    """Outcome lobe event payloads (game-profile specific)."""

    event_name: str  # e.g., "snap", "kill", "down_advanced"
    profile_id: str  # "ncaa_football_27" | "call_of_duty"
    confidence: float
    fields: dict[str, Any]  # profile-specific fields


@dataclass
class VisualPayload:
    """Visual lobe event payloads."""

    game_state: str | None = None
    game_title: str | None = None
    game_category: str | None = None  # "football" | "shooter"
    confidence: float | None = None
    frame_hash: str | None = None
    # Game-specific fields (football)
    football_home_score: int | None = None
    football_away_score: int | None = None
    football_quarter: int | None = None
    football_down: int | None = None
    football_yards_to_go: int | None = None
    football_possession: str | None = None
    football_clock_seconds: int | None = None
    football_play_clock: int | None = None
    # Game-specific fields (shooter)
    health: float | None = None
    ammo: int | None = None
    kills: int | None = None
    deaths: int | None = None


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
    session_head_ns: int | None = None,
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


# CIVIF coach-1 lives in qoresence.core.civif_tick (dataclass, not Pydantic).
from qoresence.core.civif_tick import CoachingReport as CoachingReport  # noqa: E402,F401
