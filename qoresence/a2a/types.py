"""Typed A2A messages for Gemini scene ↔ DeepSeek chat negotiation."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


def _msg_id() -> str:
    return uuid.uuid4().hex[:12]


def _now_ns() -> int:
    return time.monotonic_ns()


A2AKind = Literal[
    "scene_proposal",
    "chat_proposal",
    "need_look",
    "veto",
    "commit_act",
]


# ──────────────────────────────────────────────────────────────────────────────
# EVIDENCE CHAIN (Trio Principle 4: Every decision carries its evidence)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class EventRef:
    """A reference to a bus event by type, clock_ns, and source lobe."""

    event_type: str
    clock_ns: int
    source_lobe: str
    event_name: str | None = None  # for OUTCOME_EVENT, the specific event_name
    summary: str = ""  # short human-readable description

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FieldProvenance:
    """Provenance for a single cited field value."""

    field_name: str
    value: Any
    source: str  # "vlm" | "ocr" | "controller" | "fusion" | "outcome"
    confidence: float = 0.0
    frame_hash: str | None = None
    model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceChain:
    """Structured evidence chain accompanying a decision (Trio P4).

    Every commit_act that reaches the deck feed or Twitch chat must
    carry an evidence chain citing the specific events, fields, and
    signals that supported the decision.
    """

    cited_events: list[EventRef] = field(default_factory=list)
    cited_fields: list[FieldProvenance] = field(default_factory=list)
    coupling_score: float | None = None
    drive_phase: str | None = None
    trigger_reason: str = ""
    scene_model: str = ""
    chat_model: str = ""
    confidence: float = 0.0  # calibrated overall confidence (0..1)
    policy_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cited_events": [e.to_dict() for e in self.cited_events],
            "cited_fields": [f.to_dict() for f in self.cited_fields],
            "coupling_score": self.coupling_score,
            "drive_phase": self.drive_phase,
            "trigger_reason": self.trigger_reason,
            "scene_model": self.scene_model,
            "chat_model": self.chat_model,
            "confidence": self.confidence,
            "policy_refs": self.policy_refs,
        }


@dataclass
class SceneProposal:
    """Gemini (or stub): sparse scene description — no invented scores."""

    summary: str
    tension: float = 0.5  # 0..1
    tags: list[str] = field(default_factory=list)
    soft_only: bool = True
    frame_seq: int | None = None
    coupling: float | None = None
    drive_phase: str | None = None
    model: str = "stub"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChatProposal:
    """DeepSeek (or stub): proposed chat line for ClutchBot."""

    text: str
    path: str = "fast"  # fast | confirm
    persona: str = "neutral"
    soft_only: bool = True
    based_on_scene: str | None = None
    model: str = "stub"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NeedLook:
    """Agent requests more visual context (orchestrator may attach frame)."""

    reason: str
    from_agent: str = "deepseek"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Veto:
    """Local policy or agent rejects a proposal."""

    reason: str
    path: str = "policy"
    rejected_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CommitAct:
    """Approved act that may reach ClutchBot / Deck."""

    action: str  # chat | clip | none
    text: str
    path: str = "fast"  # fast | confirm
    factual: bool = False
    reason: str = "a2a_commit"
    payload: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] | None = None  # EvidenceChain.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class A2AMessage:
    """Envelope on the A2A bus."""

    kind: A2AKind
    body: dict[str, Any]
    from_agent: str
    to_agent: str = "*"
    msg_id: str = field(default_factory=_msg_id)
    clock_ns: int = field(default_factory=_now_ns)
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "body": self.body,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "msg_id": self.msg_id,
            "clock_ns": self.clock_ns,
            "session_id": self.session_id,
        }
