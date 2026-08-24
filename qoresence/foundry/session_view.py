"""Session Theater view model — fail-closed presentation of narrative-1 packs.

LockedValue is the only path that may emit score/yard digits. Unbodied HID
names are omitted. Missing fields stay absent (never zero / guessed buttons).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qoresence.core.civif_tick import EVENT_SCHEMA

VIEW_SCHEMA = "session-view-1"
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "deck" / "session_fixtures"
ALLOWED_FIXTURES = frozenset(
    {
        "bodied_locked",
        "unbodied_locked",
        "bodied_unlocked",
        "empty_not_persisted",
        "empty_persisted",
    }
)

_PRESS_TYPES = frozenset({"press_to_score", "spam_window"})
_HID_KEYS = frozenset({"button", "name", "button_name", "hid", "btn", "control"})
_ALT_SCORE_KEYS = frozenset(
    {
        "home_score",
        "away_score",
        "home",
        "away",
        "yard",
        "yl",
        "red_zone",
    }
)


def format_timestamp(clock_ns: int) -> str:
    ms = max(0, int(clock_ns or 0) // 1_000_000)
    minutes, rem = divmod(ms, 60_000)
    seconds, millis = divmod(rem, 1000)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _score(sit: dict[str, Any] | None, *, locked: bool) -> dict[str, int] | None:
    if not locked or not sit:
        return None
    home = _int_or_none(sit.get("home_score"))
    away = _int_or_none(sit.get("away_score"))
    if home is None or away is None:
        return None
    return {"home": home, "away": away}


def _yard(sit: dict[str, Any] | None, *, locked: bool) -> int | None:
    if not locked or not sit:
        return None
    return _int_or_none(sit.get("yard_line"))


def _input_view(inp: dict[str, Any] | None, *, bodied: bool) -> dict[str, Any] | None:
    if not isinstance(inp, dict):
        return None
    out: dict[str, Any] = {}
    if inp.get("latency_ns") is not None:
        out["latency_ns"] = _int_or_none(inp.get("latency_ns"))
    if inp.get("count") is not None:
        out["count"] = _int_or_none(inp.get("count"))
    if inp.get("press_clock_ns") is not None:
        out["press_clock_ns"] = _int_or_none(inp.get("press_clock_ns"))
    if bodied:
        btn = inp.get("button")
        if btn:
            out["button"] = str(btn)
    return out or None


def _empty_view(*, persisted: bool = False) -> dict[str, Any]:
    return {
        "schema_version": VIEW_SCHEMA,
        "session_id": "",
        "controller_bodied": False,
        "board_locked": False,
        "persisted": bool(persisted),
        "events": [],
        "confirmed": {"available": False, "score": None, "yard_line": None},
        "current_moment": None,
        "next_signal": {"kind": "awaiting", "label": "Awaiting event", "event_id": None},
        "empty_reason": "no_events" if persisted else "not_persisted",
        "plane": "qoresence-observation",
        "read_only": True,
    }


def _qualification(event_type: str, *, locked: bool, bodied: bool) -> str:
    if event_type in _PRESS_TYPES and (not bodied or not locked):
        return "suppressed"
    if event_type == "situation_shift" and not locked:
        return "suppressed"
    if locked:
        return "confirmed"
    return "unavailable"


def normalize_event(
    raw: dict[str, Any],
    *,
    board_locked: bool,
    controller_bodied: bool,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    sit = raw.get("situation_summary") if isinstance(raw.get("situation_summary"), dict) else None
    if sit is None and isinstance(raw.get("situation"), dict):
        sit = raw.get("situation")
    inp = raw.get("input_summary") if isinstance(raw.get("input_summary"), dict) else None
    if inp is None and isinstance(raw.get("input"), dict):
        inp = raw.get("input")
    ev = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
    event_type = str(raw.get("event_type") or "unknown")
    t0 = _int_or_none(raw.get("t_start_ns")) or 0
    t1 = _int_or_none(raw.get("t_end_ns")) or t0
    clips_raw = ev.get("clip_ids") if isinstance(ev.get("clip_ids"), list) else []
    clips = [str(c) for c in clips_raw if c]
    coach_type = str(ev.get("coach_type") or "") or None
    return {
        "event_id": str(raw.get("event_id") or ""),
        "event_type": event_type,
        "session_id": str(raw.get("session_id") or ""),
        "t_start_ns": t0,
        "t_end_ns": t1,
        "timestamp": format_timestamp(t0),
        "state": "locked" if board_locked else "unlocked",
        "bodied": bool(controller_bodied),
        "score": _score(sit, locked=board_locked),
        "yard_line": _yard(sit, locked=board_locked),
        "input": _input_view(inp, bodied=controller_bodied),
        "coach_context": {
            "available": bool(coach_type),
            "coach_type": coach_type,
        },
        "clip_ids": clips,
        "qualification": _qualification(event_type, locked=board_locked, bodied=controller_bodied),
        "schema_version": str(raw.get("schema_version") or EVENT_SCHEMA),
    }


def _confirmed(events: list[dict[str, Any]], *, locked: bool) -> dict[str, Any]:
    if not locked:
        return {"available": False, "score": None, "yard_line": None}
    score = None
    yard = None
    for ev in events:
        if ev.get("score") is not None:
            score = ev["score"]
        if ev.get("yard_line") is not None:
            yard = ev["yard_line"]
    return {"available": score is not None or yard is not None, "score": score, "yard_line": yard}


def _next_signal(events: list[dict[str, Any]]) -> dict[str, Any]:
    for ev in reversed(events):
        ctx = ev.get("coach_context") or {}
        if ctx.get("available"):
            return {"kind": "coach", "label": f"Coach · {ctx.get('coach_type')}", "event_id": ev.get("event_id")}
    return {"kind": "awaiting", "label": "Awaiting event", "event_id": None}


def normalize_pack(pack: dict[str, Any] | None) -> dict[str, Any]:
    try:
        raw = pack if isinstance(pack, dict) else {}
        locked = bool(raw.get("board_locked"))
        bodied = bool(raw.get("controller_bodied"))
        src = raw.get("events")
        rows = [e for e in src if isinstance(e, dict)] if isinstance(src, list) else []
        events = [
            normalize_event(e, board_locked=locked, controller_bodied=bodied) for e in rows
        ]
        events.sort(key=lambda e: (int(e["t_start_ns"]), str(e["event_id"])))
        persisted = bool(raw.get("persisted")) or bool(raw.get("path"))
        empty_reason = None
        if not events:
            empty_reason = "not_persisted" if not persisted else "no_events"
        current = events[-1] if events else None
        view = {
            "schema_version": VIEW_SCHEMA,
            "session_id": str(raw.get("session_id") or ""),
            "controller_bodied": bodied,
            "board_locked": locked,
            "persisted": persisted,
            "events": events,
            "confirmed": _confirmed(events, locked=locked),
            "current_moment": current,
            "next_signal": _next_signal(events),
            "empty_reason": empty_reason,
            "plane": "qoresence-observation",
            "read_only": True,
        }
        _assert_no_bypass(view, locked=locked, bodied=bodied)
        return view
    except Exception:
        return _empty_view(persisted=False)


def _assert_no_bypass(view: dict[str, Any], *, locked: bool, bodied: bool) -> None:
    """Drop leftover alternate keys if a future field lands on the view."""
    if locked and bodied:
        return
    for ev in view.get("events") or []:
        if not locked:
            ev["score"] = None
            ev["yard_line"] = None
            for key in _ALT_SCORE_KEYS:
                ev.pop(key, None)
        if not bodied:
            inp = ev.get("input")
            if isinstance(inp, dict):
                for key in _HID_KEYS:
                    inp.pop(key, None)
                ev["input"] = inp or None


def locked_value_html(confirmed: dict[str, Any]) -> str:
    """Only numeral emitter for score/yard. Unlocked → unavailable copy."""
    if not confirmed.get("available"):
        return '<p class="UnavailableValue">Awaiting confirmed board state</p>'
    bits: list[str] = []
    score = confirmed.get("score")
    if isinstance(score, dict) and score.get("home") is not None and score.get("away") is not None:
        bits.append(
            f'<span class="LockedValue" data-kind="score">{int(score["home"])}–{int(score["away"])}</span>'
        )
    yard = confirmed.get("yard_line")
    if yard is not None:
        bits.append(f'<span class="LockedValue" data-kind="yard">{int(yard)}</span>')
    return "".join(bits) or '<p class="UnavailableValue">Awaiting confirmed board state</p>'


def list_fixtures() -> list[str]:
    if not FIXTURE_DIR.is_dir():
        return []
    return sorted(p.stem for p in FIXTURE_DIR.glob("*.json"))


def fixture_stem(name: str) -> str | None:
    stem = Path(str(name or "")).name
    if stem.endswith(".json"):
        stem = stem[:-5]
    if stem not in ALLOWED_FIXTURES:
        return None
    return stem


def load_fixture(name: str) -> dict[str, Any]:
    stem = fixture_stem(name)
    if stem is None:
        raise FileNotFoundError(name)
    path = FIXTURE_DIR / f"{stem}.json"
    if not path.is_file():
        raise FileNotFoundError(stem)
    return json.loads(path.read_text(encoding="utf-8"))


def view_from_fixture(name: str) -> dict[str, Any]:
    return normalize_pack(load_fixture(name))
