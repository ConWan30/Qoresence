"""CIVIF live tick + highlight schemas (observation plane).

Clip sidecars stay ``civif-v0``. Live ticks use ``civif_tick-1``.
Bump ``CIVIF_TICK_SCHEMA`` on breaking field changes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from qoresence.core.coupled_event import (
    CIVIF_PLANE,
    CIVIF_SCHEMA,
    CIVIF_TICK_SCHEMA,
    IVC_VERSION,
    current_situation,
    empty_situation,
    input_bodied,
)

COACH_SCHEMA = "coach-1"
EVENT_SCHEMA = "event-1"


@dataclass
class InputTickItem:
    button: str
    edge_type: str  # press | release | move
    clock_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {"button": self.button, "edge_type": self.edge_type, "clock_ns": int(self.clock_ns)}


@dataclass
class SituationSnapshot:
    home_score: int | None = None
    away_score: int | None = None
    down: int | None = None
    distance: int | None = None
    yard_line: int | None = None
    clutch_score: float | None = None
    game_profile: str | None = None
    clutch_kind: str | None = None
    clock: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CoupledTickRecord:
    session_id: str
    clock_ns: int
    frame_seq: int
    input_ticks: list[InputTickItem]
    situation: SituationSnapshot | None
    board_locked: bool
    controller_bodied: bool
    ivc_version: str = IVC_VERSION
    schema_version: str = CIVIF_TICK_SCHEMA
    plane: str = CIVIF_PLANE
    coupling: dict[str, Any] = field(default_factory=dict)
    body_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        ticks = [] if not self.controller_bodied else [t.to_dict() for t in self.input_ticks]
        sit = None
        sit_legacy = empty_situation()
        if self.board_locked and self.situation is not None:
            sit = self.situation.to_dict()
            sit_legacy = {
                "board_locked": True,
                "home_score": self.situation.home_score,
                "away_score": self.situation.away_score,
                "down": self.situation.down,
                "distance": self.situation.distance,
                "clock": self.situation.clock or "",
                "clutch_kind": self.situation.clutch_kind or "",
                "game_title": self.situation.game_profile or "",
            }
        else:
            sit_legacy["board_locked"] = False
        return {
            "schema_version": self.schema_version,
            "sidecar_schema": CIVIF_SCHEMA,
            "plane": self.plane,
            "kind": "live_tick",
            "session_id": self.session_id,
            "clock_ns": int(self.clock_ns),
            "frame_seq": int(self.frame_seq),
            "input_ticks": ticks,
            "situation_snapshot": sit,
            "board_locked": bool(self.board_locked),
            "controller_bodied": bool(self.controller_bodied),
            "ivc_version": self.ivc_version,
            "video": {
                "t_start_ns": min([int(self.clock_ns)] + [int(t["clock_ns"]) for t in ticks])
                if ticks
                else int(self.clock_ns),
                "t_end_ns": int(self.clock_ns),
                "frame_seq": int(self.frame_seq),
            },
            "input": {
                "bodied": bool(self.controller_bodied),
                "events": ticks,
                "reason": self.body_reason,
            },
            "situation": sit_legacy,
            "coupling": dict(self.coupling or {}),
        }


@dataclass
class HighlightRecord:
    clip_id: str
    session_id: str
    coupling_score: float
    board_locked: bool
    controller_bodied: bool
    explanation: dict[str, Any]
    clip_path: str | None = None
    stem: str = ""
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "stem": self.stem or self.clip_id,
            "session_id": self.session_id,
            "coupling_score": self.coupling_score,
            "board_locked": bool(self.board_locked),
            "controller_bodied": bool(self.controller_bodied),
            "explanation": dict(self.explanation or {}),
            "clip_path": self.clip_path,
            "clip": self.clip_path,
            "score": round(float(self.score), 3),
            "why": [
                k
                for k, v in (self.explanation or {}).items()
                if v not in (None, False, "", [], 0, 0.0)
                and k
                in {"coupling_score", "board_locked", "controller_bodied", "situation_present"}
            ],
            "civif": {
                "bodied": bool(self.controller_bodied),
                "board_locked": bool(self.board_locked),
                "coupling_score": self.coupling_score,
                "home_score": (self.explanation or {}).get("home_score"),
                "away_score": (self.explanation or {}).get("away_score"),
            },
        }


@dataclass
class CoachingReport:
    """Reserved shape for a future read-only civif_coaching_report tool."""

    session_id: str
    schema_version: str = COACH_SCHEMA
    timing_stats: dict[str, Any] | None = None
    pattern_issues: list[str] | None = None
    recommendations: list[str] | None = None
    linked_clip_ids: list[str] | None = None


@dataclass
class EventRecord:
    """Reserved shape for a future coupled event / narrative layer."""

    session_id: str
    event_id: str
    event_type: str
    t_start_ns: int
    t_end_ns: int
    frame_start: int
    frame_end: int
    input_summary: dict[str, Any] | None = None
    situation_summary: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    schema_version: str = EVENT_SCHEMA


def map_edge_type(kind: str, value: float = 0.0) -> str:
    k = str(kind or "").lower()
    if k == "release":
        return "release"
    if k == "press":
        return "press"
    if k == "trigger":
        return "press" if float(value or 0) > 0.15 else "release"
    return "move"


def situation_snapshot_from_live(sit: dict[str, Any] | None) -> tuple[bool, SituationSnapshot | None]:
    raw = sit if isinstance(sit, dict) else empty_situation()
    locked = bool(raw.get("board_locked"))
    if not locked:
        return False, None
    clutch = None
    try:
        if raw.get("clutch_score") is not None:
            clutch = float(raw["clutch_score"])
    except (TypeError, ValueError):
        clutch = None
    snap = SituationSnapshot(
        home_score=raw.get("home_score"),
        away_score=raw.get("away_score"),
        down=raw.get("down"),
        distance=raw.get("distance"),
        yard_line=raw.get("yard_line"),
        clutch_score=clutch,
        game_profile=str(raw.get("game_title") or raw.get("game_profile") or "") or None,
        clutch_kind=str(raw.get("clutch_kind") or "") or None,
        clock=str(raw.get("clock") or "") or None,
    )
    return True, snap


def input_ticks_from_events(events: list[Any], *, bodied: bool) -> list[InputTickItem]:
    if not bodied:
        return []
    out: list[InputTickItem] = []
    for ev in events or []:
        if hasattr(ev, "name"):
            name = str(ev.name or "")
            kind = str(ev.kind or "")
            ns = int(getattr(ev, "clock_ns", 0) or 0)
            val = float(getattr(ev, "value", 0) or 0)
        elif isinstance(ev, dict):
            name = str(ev.get("name") or ev.get("button") or "")
            kind = str(ev.get("kind") or "")
            ns = int(ev.get("clock_ns") or 0)
            try:
                val = float(ev.get("value") or 0)
            except (TypeError, ValueError):
                val = 0.0
        else:
            continue
        if not name or ns <= 0:
            continue
        out.append(InputTickItem(button=name, edge_type=map_edge_type(kind, val), clock_ns=ns))
        if len(out) >= 64:
            break
    return out


def build_coupled_tick(
    *,
    coupling: dict[str, Any],
    events: list[Any] | None = None,
    session_id: str = "",
) -> CoupledTickRecord:
    coup = dict(coupling or {})
    dicts: list[dict[str, Any]] = []
    for e in events or []:
        if hasattr(e, "to_dict"):
            dicts.append(e.to_dict())
        elif isinstance(e, dict):
            dicts.append(e)
    bodied, reason = input_bodied(dicts, coup)
    sit_raw = current_situation()
    locked, snap = situation_snapshot_from_live(sit_raw)
    ticks = input_ticks_from_events(events or [], bodied=bodied)
    return CoupledTickRecord(
        session_id=session_id or "",
        clock_ns=int(coup.get("video_clock_ns") or 0),
        frame_seq=int(coup.get("frame_seq") or 0),
        input_ticks=ticks,
        situation=snap if locked else None,
        board_locked=locked,
        controller_bodied=bodied,
        coupling=coup,
        body_reason=reason,
    )
