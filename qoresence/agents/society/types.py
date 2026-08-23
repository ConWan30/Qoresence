"""Agent Society types — observation plane only."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Role = str

KNOWN_ROLES: tuple[str, ...] = ()

Action = Literal["advise", "propose_cut", "veto", "note", "audit", "allow"]


@dataclass
class AgentPacket:
    """Structured context. Scores only when locked. No raw frames by default."""

    session_id: str = ""
    clock_ns: int = 0
    situation: dict[str, Any] = field(default_factory=dict)
    score_vlm_locked: bool = False
    confirm_ticket_id: str = ""
    drive_graph: dict[str, Any] = field(default_factory=dict)
    last_commits: list[dict[str, Any]] = field(default_factory=list)
    health: dict[str, Any] = field(default_factory=dict)
    clip_hits: list[dict[str, Any]] = field(default_factory=list)
    path: str = ""
    phrase: str = "IDLE"
    coupling_ticket_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentReceipt:
    role: str
    action: Action
    text: str = ""
    refs: dict[str, Any] = field(default_factory=dict)
    model: str = "rules"
    ts_ns: int = 0
    policy_ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
