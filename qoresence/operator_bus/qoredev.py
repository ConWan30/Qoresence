"""Qoredev landing sequence — observation plane, offline composer.

Query-only. Reads a snapshot dict. Never emits on RetinaEventBus or the
A2A bus. Never opens capture. Never reads the pad. Not wired to Deck
health JSON (that was the #155 cut).

Sequence: physical → clock → lock → glass → story.

``next`` is the first unlicensed step among physical/clock/lock/glass.
Empty story is HOLD density, not a ticket for new narrative types.
Score digits are scrubbed from evidence. The receipt is an existing
``qoresence-operator-bus-1`` envelope — not a new live schema.
"""

from __future__ import annotations

from typing import Any

from qoresence.operator_bus.envelope import PLANE, OperatorEnvelope, parse_envelope

_SCORE_KEYS = frozenset(
    {"home_score", "away_score", "score_home", "score_away", "board", "scoreline"}
)

STEPS = ("physical", "clock", "lock", "glass", "story")
LANDING = ("physical", "clock", "lock", "glass")
BOT = "qoredev"


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


def _scrub(evidence: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in evidence.items() if k not in _SCORE_KEYS}


def _step(
    name: str,
    *,
    licensed: bool,
    kind: str,
    path: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "licensed": bool(licensed),
        "kind": kind,
        "path": path,
        "evidence": _scrub(evidence),
    }


def physical_from_video(video: dict[str, Any] | None) -> dict[str, Any]:
    vid = video if isinstance(video, dict) else {}
    age = vid.get("age_s")
    age_f = _f(age, 99.0) if age is not None else 99.0
    has = bool(vid.get("has_frame"))
    frames = _i(vid.get("frames")) or 0
    if has and age is not None and age_f < 1.0:
        kind, licensed = "live", True
    elif age is not None and age_f >= 5.0:
        kind, licensed = "freeze", False
    elif has:
        kind, licensed = "watch", False
    else:
        kind, licensed = "no_frame", False
    return _step(
        "physical",
        licensed=licensed,
        kind=kind,
        path="fast",
        evidence={"age_s": age, "has_frame": has, "frames": frames},
    )


def clock_from_stamps(
    clock_ns: int | None,
    frame_seq: int | None,
) -> dict[str, Any]:
    """FrameHub stamps only. Empty HID is valid — this step does not read the pad."""
    ns = _i(clock_ns) or 0
    seq = _i(frame_seq)
    if seq is not None and ns > 0:
        kind, licensed = "ticking", True
    elif seq is None:
        kind, licensed = "no_seq", False
    else:
        kind, licensed = "no_clock", False
    return _step(
        "clock",
        licensed=licensed,
        kind=kind,
        path="fast",
        evidence={"clock_ns": ns, "frame_seq": seq},
    )


def lock_from_tickets(
    *,
    confirm_ticket_id: str = "",
    score_vlm_locked: bool = False,
) -> dict[str, Any]:
    tid = str(confirm_ticket_id or "").strip()
    locked = bool(score_vlm_locked)
    if tid and locked:
        kind, licensed = "licensed", True
    elif locked:
        kind, licensed = "flag_only", False
    else:
        kind, licensed = "unlocked", False
    return _step(
        "lock",
        licensed=licensed,
        kind=kind,
        path="confirm",
        evidence={"confirm_ticket_id": tid, "score_vlm_locked": locked},
    )


def glass_from_deck(
    clients: Any = 0,
    glass: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """SPA name or client count from the snapshot. Does not stat the filesystem."""
    g = glass if isinstance(glass, dict) else {}
    js = str(g.get("js") or "").strip()
    spa = bool(js) and js != "none"
    n = _i(clients) or 0
    if n >= 1:
        kind, licensed = "clients", True
    elif spa:
        kind, licensed = "spa", True
    else:
        kind, licensed = "dark", False
    return _step(
        "glass",
        licensed=licensed,
        kind=kind,
        path="fast",
        evidence={"clients": n, "js": js or None, "spa": spa},
    )


def story_from_pack(story: dict[str, Any] | None) -> dict[str, Any]:
    """Honest empty is licensed. Do not mint narrative types from darkness."""
    pack = story if isinstance(story, dict) else {}
    status = str(pack.get("status") or "").strip() or "empty"
    events = _i(pack.get("event_count"))
    if events is None:
        raw = pack.get("events")
        events = len(raw) if isinstance(raw, list) else 0
    schema = str(pack.get("schema") or "").strip()
    if status in {"persisted", "live"} or events > 0:
        kind, licensed, status = "persisted", True, "persisted"
    elif status in {"absent", "unavailable"}:
        kind, licensed = "absent", True
    else:
        kind, licensed, status = "empty", True, status if status else "empty"
    return _step(
        "story",
        licensed=licensed,
        kind=kind,
        path="confirm",
        evidence={
            "status": status,
            "event_count": events,
            "schema": schema or None,
        },
    )


def _extract(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snap = snapshot if isinstance(snapshot, dict) else {}
    state = snap.get("state") if isinstance(snap.get("state"), dict) else {}
    video = snap.get("video") if isinstance(snap.get("video"), dict) else {}
    if not video:
        video = state.get("video") if isinstance(state.get("video"), dict) else {}
    sit = snap.get("situation") if isinstance(snap.get("situation"), dict) else {}
    if not sit:
        sit = state.get("situation") if isinstance(state.get("situation"), dict) else {}
    confirm = snap.get("confirm") if isinstance(snap.get("confirm"), dict) else {}
    if not confirm:
        confirm = state.get("confirm") if isinstance(state.get("confirm"), dict) else {}
    last_confirm = (
        confirm.get("last_confirm") if isinstance(confirm.get("last_confirm"), dict) else {}
    )
    glass = snap.get("glass") if isinstance(snap.get("glass"), dict) else {}
    story = snap.get("story") if isinstance(snap.get("story"), dict) else {}
    tid = str(
        sit.get("confirm_ticket_id")
        or last_confirm.get("id")
        or last_confirm.get("ticket_id")
        or ""
    ).strip()
    locked = bool(
        sit.get("score_vlm_locked")
        or sit.get("scoreboard_locked")
        or last_confirm.get("score_vlm_locked")
    )
    clock_ns = _i(sit.get("clock_ns") or video.get("clock_ns")) or 0
    frame_seq = _i(
        sit.get("frame_seq") or video.get("seq") or video.get("hub_seq") or video.get("live_seq")
    )
    return {
        "video": video,
        "clock_ns": clock_ns,
        "frame_seq": frame_seq,
        "confirm_ticket_id": tid,
        "score_vlm_locked": locked,
        "clients": snap.get("clients", 0),
        "glass": glass,
        "story": story if story else {"status": "empty", "event_count": 0},
    }


def _text(steps: dict[str, dict[str, Any]], nxt: str) -> str:
    phys = steps["physical"]
    clock = steps["clock"]
    lock = steps["lock"]
    story = steps["story"]
    if nxt == "physical":
        if phys["kind"] == "freeze":
            age = phys["evidence"].get("age_s")
            return f"physical dark: freeze age {age}s — next physical"
        if phys["kind"] == "no_frame":
            return "physical dark: no HDMI frame — next physical"
        return "physical dark: aperture watch — next physical"
    if nxt == "clock":
        if clock["kind"] == "no_seq":
            return "clock dark: no FrameHub seq — next clock"
        return "clock dark: no clock_ns — next clock"
    if nxt == "lock":
        if lock["kind"] == "flag_only":
            return "lock dark: score_vlm_locked without confirm ticket — next lock"
        return "lock dark: no confirm ticket — next lock"
    if nxt == "glass":
        return "glass dark: no SPA and no Deck clients — next glass"
    if story["kind"] == "persisted":
        return "physical→clock→lock→glass live; story persisted — HOLD"
    return "physical→clock→lock→glass live; story empty — HOLD"


def sequence_from_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Compose step rows. Query-only. No bus emit. No Deck import."""
    bag = _extract(snapshot)
    rows = [
        physical_from_video(bag["video"]),
        clock_from_stamps(bag["clock_ns"], bag["frame_seq"]),
        lock_from_tickets(
            confirm_ticket_id=bag["confirm_ticket_id"],
            score_vlm_locked=bag["score_vlm_locked"],
        ),
        glass_from_deck(bag["clients"], bag["glass"]),
        story_from_pack(bag["story"]),
    ]
    by_name = {r["name"]: r for r in rows}
    nxt = "hold"
    for name in LANDING:
        if not by_name[name]["licensed"]:
            nxt = name
            break
    path = "confirm" if nxt == "lock" else "fast"
    return {
        "next": nxt,
        "path": path,
        "clock_ns": bag["clock_ns"],
        "frame_seq": bag["frame_seq"],
        "text": _text(by_name, nxt),
        "steps": rows,
    }


def sequence_envelope(snapshot: dict[str, Any] | None) -> OperatorEnvelope:
    """Existing operator-bus envelope. kind=hold when next is hold, else fact."""
    seq = sequence_from_snapshot(snapshot)
    nxt = seq["next"]
    return parse_envelope(
        {
            "from": BOT,
            "to": "grok-build",
            "kind": "hold" if nxt == "hold" else "fact",
            "path": seq["path"],
            "plane": PLANE,
            "text": seq["text"],
            "clock_ns": seq["clock_ns"],
            "frame_seq": seq["frame_seq"],
            "evidence": {
                "next": nxt,
                "steps": {s["name"]: s["kind"] for s in seq["steps"]},
            },
        }
    )


def qoredev_health(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Fail-closed envelope dict. Offline. Not a Deck route."""
    try:
        env = sequence_envelope(snapshot)
        return env.to_dict()
    except Exception:
        return parse_envelope(
            {
                "from": BOT,
                "to": "grok-build",
                "kind": "fact",
                "path": "fast",
                "text": "physical dark: sequence unavailable — next physical",
                "evidence": {"next": "physical"},
            }
        ).to_dict()


def main() -> int:
    """stdin JSON snapshot → one operator-bus envelope on stdout. No Deck."""
    import json
    import sys

    raw = sys.stdin.read()
    if not raw.strip():
        snap: dict[str, Any] = {}
    else:
        obj = json.loads(raw)
        snap = obj if isinstance(obj, dict) else {}
    print(json.dumps(qoredev_health(snap), separators=(",", ":")))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
