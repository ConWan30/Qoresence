"""Clock-licensed actuators — Aperture, Bind, License, Arm.

Thin adapters over existing health, IVC, tickets, and clip policy.
Observation plane only. Never opens capture. Never emits a bus event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KNOWN_ACTUATORS = ("aperture", "bind", "license", "arm")
CLIMAX_ARM = 0.65


@dataclass
class ActuatorReceipt:
    actuator: str
    path: str
    clock_ns: int = 0
    frame_seq: int | None = None
    ticket_id: str = ""
    kind: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "actuator": self.actuator,
            "path": self.path,
            "clock_ns": int(self.clock_ns or 0),
            "frame_seq": self.frame_seq,
            "ticket_id": self.ticket_id,
            "kind": self.kind,
            "evidence": dict(self.evidence),
            "text": self.text,
        }


def registry() -> list[dict[str, Any]]:
    return [
        {
            "name": "aperture",
            "inputs": ["video.age_s", "has_frame", "frames"],
            "outputs": ["receipt"],
            "path": "fast",
            "requires_ticket": False,
        },
        {
            "name": "bind",
            "inputs": ["pll_lock", "binds", "lag_center_ms"],
            "outputs": ["receipt"],
            "path": "fast",
            "requires_ticket": False,
        },
        {
            "name": "license",
            "inputs": ["coupling_ticket_id", "confirm_ticket_id", "score_vlm_locked"],
            "outputs": ["ticket", "veto"],
            "path": "confirm",
            "requires_ticket": True,
        },
        {
            "name": "arm",
            "inputs": ["climax", "locked_score_delta", "operator_post"],
            "outputs": ["clip", "stem_suggest"],
            "path": "fast",
            "requires_ticket": False,
        },
    ]


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v: Any) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def aperture_from_video(
    video: dict[str, Any] | None,
    *,
    clock_ns: int = 0,
    frame_seq: int | None = None,
) -> ActuatorReceipt:
    vid = video if isinstance(video, dict) else {}
    age = vid.get("age_s")
    age_f = _f(age, 99.0) if age is not None else 99.0
    has = bool(vid.get("has_frame"))
    frames = _i(vid.get("frames")) or 0
    if has and age is not None and age_f < 1.0:
        kind, text = "live", "aperture live"
    elif age is not None and age_f >= 5.0:
        kind, text = "freeze", f"freeze age {age_f:.1f}s"
    else:
        kind, text = "watch", "aperture watch"
    return ActuatorReceipt(
        actuator="aperture",
        path="fast",
        clock_ns=clock_ns,
        frame_seq=frame_seq,
        kind=kind,
        text=text,
        evidence={"age_s": age, "has_frame": has, "frames": frames},
    )


def bind_from_sync(
    sync: dict[str, Any] | None,
    *,
    clock_ns: int = 0,
    frame_seq: int | None = None,
) -> ActuatorReceipt:
    s = sync if isinstance(sync, dict) else {}
    pll = bool(s.get("pll_lock"))
    binds = _i(s.get("binds")) or 0
    lag = _f(s.get("lag_center_ms"), s.get("sync_lag_ms") or 0.0)
    kind = "lock" if pll else "open"
    return ActuatorReceipt(
        actuator="bind",
        path="fast",
        clock_ns=clock_ns,
        frame_seq=frame_seq,
        kind=kind,
        text="pll lock" if pll else "pll open",
        evidence={"pll_lock": pll, "binds": binds, "lag_center_ms": lag},
    )


def license_from_tickets(
    *,
    coupling_ticket_id: str = "",
    confirm_ticket_id: str = "",
    score_vlm_locked: bool = False,
    clock_ns: int = 0,
    frame_seq: int | None = None,
) -> ActuatorReceipt:
    cid = str(coupling_ticket_id or "").strip()
    tid = str(confirm_ticket_id or "").strip()
    if cid:
        return ActuatorReceipt(
            actuator="license",
            path="fast",
            clock_ns=clock_ns,
            frame_seq=frame_seq,
            ticket_id=cid,
            kind="ticket",
            text="ticket live",
            evidence={"coupling_ticket_id": cid},
        )
    if tid or score_vlm_locked:
        return ActuatorReceipt(
            actuator="license",
            path="confirm",
            clock_ns=clock_ns,
            frame_seq=frame_seq,
            ticket_id=tid,
            kind="ticket",
            text="board licensed",
            evidence={"confirm_ticket_id": tid, "score_vlm_locked": bool(score_vlm_locked)},
        )
    return ActuatorReceipt(
        actuator="license",
        path="confirm",
        clock_ns=clock_ns,
        frame_seq=frame_seq,
        kind="veto",
        text="license veto",
        evidence={"score_vlm_locked": False},
    )


def arm_allowed(
    *,
    climax: float = 0.0,
    locked_score_delta: bool = False,
    operator_post: bool = False,
) -> bool:
    """Phase 3: climax, locked score change, or operator POST. Else no clip."""
    if operator_post or locked_score_delta:
        return True
    return _f(climax) >= CLIMAX_ARM


def stem_suggest(
    *,
    climax: float = 0.0,
    locked_score_delta: bool = False,
    operator_post: bool = False,
) -> str | None:
    """Suggest only. Conductor / operator remains mode authority."""
    if arm_allowed(
        climax=climax,
        locked_score_delta=locked_score_delta,
        operator_post=operator_post,
    ):
        return "armed"
    return None


def arm_from_policy(
    *,
    climax: float = 0.0,
    locked_score_delta: bool = False,
    operator_post: bool = False,
    clock_ns: int = 0,
    frame_seq: int | None = None,
) -> ActuatorReceipt:
    ok = arm_allowed(
        climax=climax,
        locked_score_delta=locked_score_delta,
        operator_post=operator_post,
    )
    return ActuatorReceipt(
        actuator="arm",
        path="fast",
        clock_ns=clock_ns,
        frame_seq=frame_seq,
        kind="clip" if ok else "hold",
        text="arm clip" if ok else "arm hold",
        evidence={
            "climax": _f(climax),
            "locked_score_delta": bool(locked_score_delta),
            "operator_post": bool(operator_post),
            "stem_suggest": stem_suggest(
                climax=climax,
                locked_score_delta=locked_score_delta,
                operator_post=operator_post,
            ),
        },
    )


def evaluate_actuators(snapshot: dict[str, Any] | None) -> list[ActuatorReceipt]:
    snap = snapshot if isinstance(snapshot, dict) else {}
    state = snap.get("state") if isinstance(snap.get("state"), dict) else {}
    video = snap.get("video") if isinstance(snap.get("video"), dict) else {}
    if not video:
        video = state.get("video") if isinstance(state.get("video"), dict) else {}
    coup = snap.get("coupling") if isinstance(snap.get("coupling"), dict) else {}
    if not coup:
        ctrl = snap.get("controller") if isinstance(snap.get("controller"), dict) else {}
        coup = ctrl
    sit = snap.get("situation") if isinstance(snap.get("situation"), dict) else {}
    if not sit:
        sit = state.get("situation") if isinstance(state.get("situation"), dict) else {}
    clock_ns = _i(sit.get("clock_ns") or video.get("clock_ns")) or 0
    frame_seq = _i(sit.get("frame_seq") or video.get("seq") or video.get("hub_seq"))
    companion = snap.get("companion") if isinstance(snap.get("companion"), dict) else {}
    clip = companion.get("clip") if isinstance(companion.get("clip"), dict) else {}
    coup_sit = sit.get("coupling") if isinstance(sit.get("coupling"), dict) else {}
    climax = _f(sit.get("climax_score") or coup_sit.get("climax_score"), 0.0)
    if clip.get("gates") and isinstance(clip.get("gates"), dict):
        climax = max(climax, _f(clip["gates"].get("climax")))
    return [
        aperture_from_video(video, clock_ns=clock_ns, frame_seq=frame_seq),
        bind_from_sync(coup, clock_ns=clock_ns, frame_seq=frame_seq),
        license_from_tickets(
            coupling_ticket_id=str(sit.get("coupling_ticket_id") or coup.get("coupling_ticket_id") or ""),
            confirm_ticket_id=str(sit.get("confirm_ticket_id") or ""),
            score_vlm_locked=bool(sit.get("score_vlm_locked") or sit.get("scoreboard_locked")),
            clock_ns=clock_ns,
            frame_seq=frame_seq,
        ),
        arm_from_policy(
            climax=climax,
            locked_score_delta=bool(sit.get("score_changed") or sit.get("locked_score_delta")),
            operator_post=bool(sit.get("operator_clip") or sit.get("operator_post")),
            clock_ns=clock_ns,
            frame_seq=frame_seq,
        ),
    ]


def actuators_health(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    rows = evaluate_actuators(snapshot)
    return {
        "registry": registry(),
        "receipts": [r.to_dict() for r in rows],
    }
