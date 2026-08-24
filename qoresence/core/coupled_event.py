"""CIVIF v0 — Coupled Event Record for clip sidecars.

Observation plane only. Empty DualSense on this host is valid (bodied=false).
Digits only when board_locked. Do not invent scores or input edges.
"""

from __future__ import annotations

from typing import Any

CIVIF_SCHEMA = "civif-v0"
CIVIF_PLANE = "qoresence-observation"
IVC_VERSION = "ivc-v0"


def _ns(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def event_clock_ns(ev: dict[str, Any]) -> int:
    return _ns(ev.get("clock_ns") or ev.get("video_clock_ns"))


def window_ns(data: dict[str, Any]) -> tuple[int, int]:
    video = data.get("video") if isinstance(data.get("video"), dict) else {}
    clip = data.get("clip") if isinstance(data.get("clip"), dict) else {}
    clock = clip.get("clock_ns") if isinstance(clip.get("clock_ns"), dict) else {}
    start = _ns(
        video.get("t_start_ns")
        or clock.get("start")
        or data.get("clip.clock_ns.start")
    )
    end = _ns(
        video.get("t_end_ns")
        or clock.get("end")
        or data.get("clip.clock_ns.end")
    )
    return start, end


def input_events(data: dict[str, Any]) -> list[dict[str, Any]]:
    inp = data.get("input")
    if isinstance(inp, dict) and isinstance(inp.get("events"), list):
        return [e for e in inp["events"] if isinstance(e, dict)]
    raw = data.get("input_ring_events")
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    return []


def input_bodied(events: list[dict[str, Any]], coupling: dict[str, Any]) -> tuple[bool, str]:
    if events:
        return True, "input_ring"
    if coupling.get("imu_bodied"):
        return True, "imu_bodied"
    return False, "pad_not_on_this_host"


def empty_situation() -> dict[str, Any]:
    return {
        "board_locked": False,
        "home_score": None,
        "away_score": None,
        "down": None,
        "distance": None,
        "clock": "",
        "clutch_kind": "",
        "game_title": "",
    }


def build_coupling_sidecar(
    *,
    clip_id: str,
    session_id: str,
    start_ns: int,
    end_ns: int,
    frame_start: int,
    frame_end: int,
    video_path: str,
    events: list[dict[str, Any]],
    coupling: dict[str, Any],
    coupling_history: list[Any],
    situation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    coup = dict(coupling or {})
    hist = list(coupling_history or [])
    evs = list(events or [])
    bodied, reason = input_bodied(evs, coup)
    sit = dict(situation) if situation else empty_situation()
    if not sit.get("board_locked"):
        sit["home_score"] = None
        sit["away_score"] = None
    return {
        "schema_version": CIVIF_SCHEMA,
        "plane": CIVIF_PLANE,
        "session_id": session_id or "",
        "clip_id": clip_id,
        "ivc_version": IVC_VERSION,
        "video": {
            "path": video_path,
            "frame_start": int(frame_start),
            "frame_end": int(frame_end),
            "t_start_ns": int(start_ns),
            "t_end_ns": int(end_ns),
        },
        "input": {
            "bodied": bodied,
            "events": evs,
            "reason": reason,
        },
        "situation": sit,
        # Legacy: full last IVC payload (Foundry / existing tests).
        "coupling": coup,
        "coupling_civif": {
            "score": float(coup.get("coupling") or 0.0),
            "ticket_id": str(coup.get("coupling_ticket_id") or ""),
            "pll_lock": bool(coup.get("pll_lock")),
            "history": hist,
        },
        "provenance": {
            "source_lobe": "controller",
            "ocr_confidence": None,
            "vlm_confidence": None,
        },
        # Legacy Foundry keys — keep until search_clips reads civif-v0.
        "clip": {"clock_ns": {"start": int(start_ns), "end": int(end_ns)}},
        "clip.clock_ns.start": int(start_ns),
        "clip.clock_ns.end": int(end_ns),
        "coupling_history": hist,
        "input_ring_events": evs,
    }


def validate_coupling(data: dict[str, Any]) -> list[str]:
    """Return errors. Empty list = valid. Legacy sidecars without schema_version OK."""
    errors: list[str] = []
    if not isinstance(data, dict) or not data:
        return ["sidecar is not an object"]
    ver = data.get("schema_version")
    if ver not in (None, "", CIVIF_SCHEMA):
        errors.append(f"unknown schema_version {ver!r}")
    if data.get("plane") not in (None, "", CIVIF_PLANE):
        errors.append("plane must be qoresence-observation")
    start, end = window_ns(data)
    if start and end and end < start:
        errors.append("t_end_ns before t_start_ns")
    events = input_events(data)
    clocks: list[int] = []
    for e in events:
        ns = event_clock_ns(e)
        if ns <= 0:
            errors.append("input event missing clock_ns")
            continue
        if start and ns < start:
            errors.append("input event before clip window")
        if end and ns > end:
            errors.append("input event after clip window")
        clocks.append(ns)
    if clocks != sorted(clocks):
        errors.append("input clock_ns not monotonic")
    inp = data.get("input") if isinstance(data.get("input"), dict) else None
    if inp is not None:
        bodied = bool(inp.get("bodied"))
        if bodied and not events and not (inp.get("reason") == "imu_bodied"):
            errors.append("bodied true with empty events")
        if events and inp.get("bodied") is False:
            errors.append("bodied false with events present")
    sit = data.get("situation") if isinstance(data.get("situation"), dict) else {}
    if sit.get("home_score") is not None or sit.get("away_score") is not None:
        if not sit.get("board_locked"):
            errors.append("scores without board_locked")
    return errors


_live_situation_hook = None


def set_live_situation_hook(fn: Any) -> None:
    """ClutchBot / tests register a snapshot getter. CIVIF never invents digits."""
    global _live_situation_hook
    _live_situation_hook = fn


def situation_from_live_snapshot(snap: dict[str, Any] | None) -> dict[str, Any]:
    sit = empty_situation()
    if not isinstance(snap, dict):
        return sit
    sit["game_title"] = str(snap.get("game_title") or "")
    sit["clutch_kind"] = str(snap.get("last_outcome_event") or snap.get("clutch_kind") or "")
    locked = bool(
        snap.get("board_locked")
        or snap.get("score_vlm_locked")
        or snap.get("scoreboard_locked")
    )
    sit["board_locked"] = locked
    if not locked:
        return sit
    sit["home_score"] = snap.get("home_score")
    sit["away_score"] = snap.get("away_score")
    sit["down"] = snap.get("down")
    sit["distance"] = snap.get("yards_to_go") if snap.get("yards_to_go") is not None else snap.get("distance")
    clock = snap.get("play_clock")
    if clock is None:
        clock = snap.get("clock") or ""
    sit["clock"] = clock if clock is not None else ""
    return sit


def current_situation() -> dict[str, Any]:
    hook = _live_situation_hook
    if hook is None:
        return empty_situation()
    try:
        raw = hook()
    except Exception:
        return empty_situation()
    return situation_from_live_snapshot(raw if isinstance(raw, dict) else None)


def summarize_coupling_for_index(data: dict[str, Any] | None) -> dict[str, Any]:
    """Fail-closed index card. No pad tokens unless bodied. No scores unless locked."""
    empty = {
        "present": False,
        "bodied": False,
        "board_locked": False,
        "home_score": None,
        "away_score": None,
        "coupling_score": None,
        "reason": "",
        "schema_version": "",
        "search_tokens": "",
    }
    if not isinstance(data, dict) or not data:
        return empty
    events = input_events(data)
    coup = data.get("coupling") if isinstance(data.get("coupling"), dict) else {}
    inp = data.get("input") if isinstance(data.get("input"), dict) else {}
    sit = data.get("situation") if isinstance(data.get("situation"), dict) else {}
    civ = data.get("coupling_civif") if isinstance(data.get("coupling_civif"), dict) else {}
    if inp:
        bodied = bool(inp.get("bodied"))
        reason = str(inp.get("reason") or "")
    else:
        bodied, reason = input_bodied(events, coup)
    locked = bool(sit.get("board_locked"))
    home = sit.get("home_score") if locked else None
    away = sit.get("away_score") if locked else None
    score: float | None = None
    raw_score = civ.get("score") if civ else None
    if raw_score is None:
        raw_score = coup.get("coupling")
    if raw_score is not None:
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = None
    tokens: list[str] = []
    ver = str(data.get("schema_version") or "")
    if ver:
        tokens.append(ver)
        tokens.append("civif")
    if bodied:
        tokens.append("bodied")
        for e in events:
            for key in ("name", "button", "kind"):
                val = e.get(key)
                if val:
                    tokens.append(str(val))
    else:
        tokens.append("unbodied")
        if reason:
            tokens.append(reason.replace("_", " "))
    if locked and home is not None and away is not None:
        tokens.append(f"{home}-{away}")
        tokens.append("score")
    return {
        "present": True,
        "bodied": bodied,
        "board_locked": locked,
        "home_score": home,
        "away_score": away,
        "coupling_score": score,
        "reason": reason,
        "schema_version": ver,
        "search_tokens": " ".join(tokens).lower(),
    }
