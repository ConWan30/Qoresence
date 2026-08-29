"""RCP envelope for the operator-bot mailbox.

Separate from in-process A2ABus (Gemini↔DeepSeek). Never carries unlicensed
score digits on path=fast. Never emits on RetinaEventBus.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

SCHEMA = "qoresence-operator-bus-1"
PLANE = "qoresence-observation"
KINDS = frozenset({"fact", "ticket", "veto", "patch", "hold", "admin"})
PATHS = frozenset({"fast", "confirm", "hold", "admin"})
_SCORE_KEYS = frozenset(
    {"home_score", "away_score", "score_home", "score_away", "board", "scoreline"}
)


def _id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class OperatorEnvelope:
    schema: str = SCHEMA
    id: str = field(default_factory=_id)
    frm: str = "unknown"
    to: str = "all"
    clock_ns: int = 0
    frame_seq: int | None = None
    path: str = "fast"
    plane: str = PLANE
    kind: str = "fact"
    text: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def from_(self) -> str:
        return self.frm

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "id": self.id,
            "from": self.frm,
            "to": self.to,
            "clock_ns": int(self.clock_ns or 0),
            "frame_seq": self.frame_seq,
            "path": self.path,
            "plane": self.plane,
            "kind": self.kind,
            "text": self.text,
            "evidence": dict(self.evidence),
        }


def parse_envelope(raw: dict[str, Any] | None) -> OperatorEnvelope:
    if not isinstance(raw, dict):
        raise ValueError("envelope must be an object")
    kind = str(raw.get("kind") or "").strip().lower()
    path = str(raw.get("path") or "").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    if path not in PATHS:
        raise ValueError(f"path must be one of {sorted(PATHS)}")
    text = str(raw.get("text") or "").strip()
    if not text:
        raise ValueError("text is required")
    frm = str(raw.get("from") or raw.get("frm") or "").strip()
    if not frm:
        raise ValueError("from is required")
    plane = str(raw.get("plane") or PLANE).strip() or PLANE
    if plane != PLANE:
        raise ValueError(f"plane must be {PLANE}")
    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
    if path == "fast":
        evidence = {k: v for k, v in evidence.items() if k not in _SCORE_KEYS}
    clock = raw.get("clock_ns") or 0
    try:
        clock_ns = int(clock)
    except (TypeError, ValueError):
        clock_ns = 0
    if clock_ns <= 0:
        clock_ns = time.monotonic_ns()
    seq = raw.get("frame_seq")
    try:
        frame_seq = int(seq) if seq is not None else None
    except (TypeError, ValueError):
        frame_seq = None
    eid = str(raw.get("id") or "").strip() or _id()
    return OperatorEnvelope(
        schema=SCHEMA,
        id=eid,
        frm=frm,
        to=str(raw.get("to") or "all").strip() or "all",
        clock_ns=clock_ns,
        frame_seq=frame_seq,
        path=path,
        plane=PLANE,
        kind=kind,
        text=text[:2000],
        evidence=dict(evidence),
    )
