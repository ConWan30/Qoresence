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
