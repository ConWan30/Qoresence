"""Session Theater view model — fail-closed presentation of narrative-1 packs.

LockedValue is the only path that may emit score/yard digits. Unbodied HID
names are omitted. Missing fields stay absent (never zero / guessed buttons).
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import UTC, datetime
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

_CLIP_STEM_RE = re.compile(r"^hdmi_clip_[\w\-]+$", re.I)
_CLIP_UNAVAILABLE = {"available": False}

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


def clips_dir(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.getenv("QORESENCE_CLIPS_DIR") or "clips")


def permitted_clip_stem(raw: Any) -> str | None:
    """Accept only existing-contract stems: hdmi_clip_<token>. Reject paths."""
    if raw is None or not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or text in {".", ".."}:
        return None
    if any(ch in text for ch in ("/", "\\", "%", "\x00", "\n", "\r", "\t")):
        return None
    if ".." in text:
        return None
    name = Path(text).name
    if name != text:
        return None
    lower = name.lower()
    if lower.endswith(".coupling.json"):
        name = name[: -len(".coupling.json")]
    elif lower.endswith((".mp4", ".avi")):
        name = Path(name).stem
    if not _CLIP_STEM_RE.fullmatch(name):
        return None
    return name


def resolve_event_clip(
    candidates: list[Any],
    *,
    session_id: str,
    clips_root: Path | str | None = None,
) -> dict[str, Any]:
    """Map evidence.clip_ids to a single existing /media/clips/{stem}.mp4 target."""
    sid = str(session_id or "")
    if not sid:
        return dict(_CLIP_UNAVAILABLE)
    root = clips_dir(clips_root)
    try:
        root = root.resolve()
    except OSError:
        return dict(_CLIP_UNAVAILABLE)
    for raw in candidates:
        stem = permitted_clip_stem(raw)
        if stem is None:
            continue
        media = None
        for ext in (".mp4", ".avi"):
            cand = (root / f"{stem}{ext}").resolve()
            try:
                cand.relative_to(root)
            except ValueError:
                continue
            if cand.is_file():
                media = cand
                break
        if media is None:
            continue
        sidecar = (root / f"{stem}.coupling.json").resolve()
        try:
            sidecar.relative_to(root)
        except ValueError:
            continue
        if not sidecar.is_file():
            continue
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        owner = payload.get("session_id")
        if not isinstance(owner, str) or not owner or owner != sid:
            continue
        return {"available": True, "clip_id": stem}
    return dict(_CLIP_UNAVAILABLE)


def normalize_event(
    raw: dict[str, Any],
    *,
    board_locked: bool,
    controller_bodied: bool,
    session_id: str = "",
    clips_root: Path | str | None = None,
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
    event_session = str(raw.get("session_id") or session_id or "")
    clip = resolve_event_clip(clips_raw, session_id=event_session or session_id, clips_root=clips_root)
    coach_type = str(ev.get("coach_type") or "") or None
    return {
        "event_id": str(raw.get("event_id") or ""),
        "event_type": event_type,
        "session_id": event_session,
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
        "clip": clip,
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


def normalize_pack(
    pack: dict[str, Any] | None,
    *,
    clips_root: Path | str | None = None,
) -> dict[str, Any]:
    try:
        raw = pack if isinstance(pack, dict) else {}
        locked = bool(raw.get("board_locked"))
        bodied = bool(raw.get("controller_bodied"))
        session_id = str(raw.get("session_id") or "")
        src = raw.get("events")
        rows = [e for e in src if isinstance(e, dict)] if isinstance(src, list) else []
        events = [
            normalize_event(
                e,
                board_locked=locked,
                controller_bodied=bodied,
                session_id=session_id,
                clips_root=clips_root,
            )
            for e in rows
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
        for ev in view.get("events") or []:
            ev.pop("clip_ids", None)
            clip = ev.get("clip")
            if not isinstance(clip, dict) or not clip.get("available"):
                ev["clip"] = dict(_CLIP_UNAVAILABLE)
            else:
                stem = permitted_clip_stem(clip.get("clip_id"))
                ev["clip"] = {"available": True, "clip_id": stem} if stem else dict(_CLIP_UNAVAILABLE)
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


STALE_AFTER_MS = 5000
VIEW_STATUSES = frozenset({"live", "empty", "not_persisted", "unavailable", "invalid"})

_envelope_lock = threading.Lock()
_last_envelope: dict[str, dict[str, Any]] = {}


def _iso_z(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_z(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def pack_is_invalid(pack: Any) -> bool:
    if pack is None:
        return False
    if not isinstance(pack, dict):
        return True
    events = pack.get("events", [])
    return events is not None and not isinstance(events, list)


def derive_status(view: dict[str, Any], *, invalid: bool = False, unavailable: bool = False) -> str:
    if invalid:
        return "invalid"
    if unavailable:
        return "unavailable"
    if view.get("events"):
        return "live"
    if view.get("empty_reason") == "not_persisted":
        return "not_persisted"
    return "empty"


def _apply_status_reason(view: dict[str, Any], status: str) -> None:
    if status == "invalid":
        view["empty_reason"] = "invalid"
    elif status == "unavailable":
        view["empty_reason"] = "unavailable"


def _freshness(now: datetime, *, last_event_at: str | None, generated_at: datetime | None = None) -> dict[str, Any]:
    gen = generated_at or now
    age_ms = max(0, int((now - gen).total_seconds() * 1000))
    return {
        "generated_at": _iso_z(gen),
        "last_event_at": last_event_at,
        "age_ms": age_ms,
        "stale": age_ms > STALE_AFTER_MS,
    }


def _cache_key(session_id: str, fixture: str) -> str:
    return f"{fixture or 'live'}:{session_id or '_'}"


def _load_live_pack(session_id: str) -> tuple[dict[str, Any] | None, bool]:
    """Return (pack, unavailable). Never persist. Never regenerate on GET."""
    try:
        from qoresence.foundry.narrative_engine import last_narrative

        pack = last_narrative(session_id) if session_id else last_narrative()
        return pack, False
    except Exception:
        return None, True


def _read_live_situation() -> dict[str, Any]:
    try:
        from qoresence.deck.server import _state

        sit = getattr(_state, "situation", None)
        return dict(sit) if isinstance(sit, dict) else {}
    except Exception:
        return {}


def _live_board_licensed(sit: dict[str, Any] | None) -> bool:
    """Ticket-clock law: flag-only lock must not paint digits."""
    if not isinstance(sit, dict):
        return False
    ticket = str(sit.get("confirm_ticket_id") or "").strip()
    return bool(sit.get("score_vlm_locked")) and bool(ticket)


def overlay_live_board(view: dict[str, Any], sit: dict[str, Any] | None) -> dict[str, Any]:
    """License confirmed digits from live situation lock. Does not invent events or yards."""
    if not isinstance(view, dict):
        return view
    from qoresence.vision.board_why import normalize_board_why

    if not _live_board_licensed(sit):
        why = "unlocked"
        if isinstance(sit, dict):
            flagged = bool(sit.get("score_vlm_locked") or sit.get("scoreboard_locked"))
            ticket = str(sit.get("confirm_ticket_id") or "").strip()
            if flagged and not ticket:
                why = "no_ticket"
            elif sit.get("board_why"):
                why = str(sit.get("board_why"))
        view["board_why"] = normalize_board_why(why)
        return view
    view["board_why"] = "confirm_ticket"
    view["board_locked"] = True
    home = _int_or_none(sit.get("home_score") if sit else None)
    away = _int_or_none(sit.get("away_score") if sit else None)
    yard = _int_or_none(sit.get("yard_line") if sit else None)
    score = {"home": home, "away": away} if home is not None and away is not None else None
    confirmed = {"available": False, "score": None, "yard_line": None}
    if score is not None:
        confirmed["score"] = score
        confirmed["available"] = True
    if yard is not None:
        confirmed["yard_line"] = yard
        confirmed["available"] = True
    view["confirmed"] = confirmed
    return view


def _resolve_session_id(explicit: str) -> str:
    if explicit:
        return str(explicit)
    try:
        from qoresence.core.session import SessionAuthority

        ident = SessionAuthority.current()
        if ident is not None:
            return str(ident.session_id)
    except Exception:
        pass
    return os.getenv("QORESENCE_SESSION_ID") or ""


def build_session_response(
    *,
    session_id: str = "",
    fixture: str = "",
    now: datetime | None = None,
    live_situation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read-only session-view envelope. `view` is always normalize_pack output."""
    generated = now or datetime.now(UTC)
    sid = _resolve_session_id(session_id)
    invalid = False
    unavailable = False
    pack: Any = None
    if fixture:
        try:
            pack = load_fixture(fixture)
            sid = sid or str(pack.get("session_id") or "")
        except FileNotFoundError:
            unavailable = True
            pack = None
    else:
        pack, live_unavail = _load_live_pack(sid)
        if live_unavail:
            unavailable = True
    if pack_is_invalid(pack):
        invalid = True
        view = normalize_pack(None)
    elif pack is None:
        view = normalize_pack(
            {
                "session_id": sid,
                "events": [],
                "persisted": False,
                "board_locked": False,
                "controller_bodied": False,
            }
        )
    else:
        view = normalize_pack(pack)
    if not fixture and not invalid:
        sit = live_situation if live_situation is not None else _read_live_situation()
        overlay_live_board(view, sit)
        if view.get("confirmed") and view["confirmed"].get("available"):
            view["board_why"] = "confirm_ticket"
        elif not view.get("board_why"):
            from qoresence.vision.board_why import normalize_board_why

            why = sit.get("board_why") if isinstance(sit, dict) else ""
            view["board_why"] = normalize_board_why(why or "unlocked")
    status = derive_status(view, invalid=invalid, unavailable=unavailable)
    _apply_status_reason(view, status)
    last_event_at = _iso_z(generated) if view.get("events") else None
    envelope = {
        "ok": status != "invalid",
        "status": status,
        "session": sid,
        "view": view,
        "freshness": _freshness(generated, last_event_at=last_event_at, generated_at=generated),
    }
    key = _cache_key(sid, fixture)
    if status == "unavailable" and not fixture:
        with _envelope_lock:
            prev = _last_envelope.get(key)
        if prev and prev.get("status") in {"live", "empty", "not_persisted"}:
            gen = _parse_iso_z(str((prev.get("freshness") or {}).get("generated_at") or ""))
            aged = dict(prev)
            aged["freshness"] = _freshness(
                generated,
                last_event_at=(prev.get("freshness") or {}).get("last_event_at"),
                generated_at=gen or generated,
            )
            return aged
    if status != "unavailable":
        with _envelope_lock:
            _last_envelope[key] = envelope
    return envelope


RECAP_SCHEMA = "session-recap-1"


def _usable_clock_ns(value: Any) -> int | None:
    n = _int_or_none(value)
    if n is None or n <= 0:
        return None
    return n


def _event_duration_bounds(ev: dict[str, Any]) -> tuple[int, int] | None:
    start = _usable_clock_ns(ev.get("t_start_ns"))
    end = _usable_clock_ns(ev.get("t_end_ns"))
    if start is None or end is None or end < start:
        return None
    return start, end


def _recap_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = list(enumerate(events))

    def key(item: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        idx, ev = item
        start = _usable_clock_ns(ev.get("t_start_ns"))
        if start is None:
            return (1, 0, idx)
        return (0, start, idx)

    return [ev for _i, ev in sorted(indexed, key=key)]


def recap_from_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Read-only session-recap-1 derived from a session-view envelope."""
    view = envelope.get("view") if isinstance(envelope.get("view"), dict) else {}
    status = str(envelope.get("status") or "unavailable")
    events = [e for e in (view.get("events") or []) if isinstance(e, dict)]
    ordered = _recap_events(events)
    bounds = [_event_duration_bounds(e) for e in ordered]
    usable = [b for b in bounds if b is not None]
    if usable:
        duration_ms = (max(b[1] for b in usable) - min(b[0] for b in usable)) // 1_000_000
    else:
        duration_ms = None
    empty_reason = None
    if status == "empty":
        empty_reason = "no_events"
    elif status == "not_persisted":
        empty_reason = "not_persisted"
    freshness = envelope.get("freshness") if isinstance(envelope.get("freshness"), dict) else {}
    if status == "invalid":
        freshness = {
            "generated_at": freshness.get("generated_at") or _iso_z(datetime.now(UTC)),
            "last_event_at": None,
            "age_ms": 0,
            "stale": False,
        }
        ordered = []
    return {
        "schema": RECAP_SCHEMA,
        "ok": status != "invalid",
        "status": status,
        "session": envelope.get("session") or "",
        "duration_ms": duration_ms,
        "event_count": 0 if status == "invalid" else len(ordered),
        "confirmed_event_count": 0
        if status == "invalid"
        else sum(1 for e in ordered if e.get("qualification") == "confirmed"),
        "linked_clip_count": 0
        if status == "invalid"
        else sum(1 for e in ordered if isinstance(e.get("clip"), dict) and e["clip"].get("available") is True),
        "incomplete": status == "live" and view.get("persisted") is False,
        "empty_reason": empty_reason,
        "events": ordered,
        "freshness": {
            "generated_at": freshness.get("generated_at") or _iso_z(datetime.now(UTC)),
            "last_event_at": freshness.get("last_event_at"),
            "age_ms": int(freshness.get("age_ms") or 0),
            "stale": bool(freshness.get("stale")),
        },
    }


def build_session_recap(
    *,
    session_id: str = "",
    fixture: str = "",
    now: datetime | None = None,
    live_situation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read-only recap. Does not persist or mutate session state."""
    return recap_from_envelope(
        build_session_response(
            session_id=session_id, fixture=fixture, now=now, live_situation=live_situation
        )
    )
