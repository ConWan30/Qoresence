"""NarrativeEngine — session play-by-play from CoupledTickRecords.

Observation only. Fail-closed: no button names unless bodied; no score/yard
digits unless board_locked. MCP ``civif_narrative`` is not listed.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from qoresence.core.civif_tick import EVENT_SCHEMA, EventRecord
from qoresence.foundry.pattern_coach import _presses_from_ticks, spam_windows
from qoresence.foundry.timing_coach import samples_from_ticks

log = logging.getLogger(__name__)

NARRATIVE_SCHEMA = "narrative-1"

_lock = threading.Lock()
_last: dict[str, dict[str, Any]] = {}


def last_narrative(session_id: str = "") -> dict[str, Any] | None:
    with _lock:
        if session_id:
            return _last.get(str(session_id))
        if not _last:
            return None
        return next(reversed(_last.values()))


def _log_enabled() -> bool:
    return os.getenv("QORESENCE_CIVIF_NARRATIVE_LOG", "").strip().lower() in {"1", "true", "on"}


def _eid(session_id: str, n: int) -> str:
    sid = session_id or "session"
    return f"{sid}_evt_{n:04d}"


def _sit_summary(sit: dict[str, Any], *, locked: bool) -> dict[str, Any] | None:
    if not locked or not sit:
        return None
    out: dict[str, Any] = {"board_locked": True}
    if sit.get("home_score") is not None:
        out["home_score"] = sit.get("home_score")
    if sit.get("away_score") is not None:
        out["away_score"] = sit.get("away_score")
    yl = sit.get("yard_line")
    if yl is not None:
        try:
            n = int(yl)
            out["yard_line"] = n
            out["red_zone"] = n <= 20
        except (TypeError, ValueError):
            pass
    if sit.get("clutch_score") is not None:
        out["clutch_score"] = sit.get("clutch_score")
    return out or None


def _sit_at(ticks: list[dict[str, Any]], clock_ns: int) -> dict[str, Any]:
    best: dict[str, Any] = {}
    for t in ticks:
        if int(t.get("clock_ns") or 0) > clock_ns:
            continue
        sit = t.get("situation") if isinstance(t.get("situation"), dict) else {}
        if sit.get("board_locked"):
            best = sit
    return best


def _frame(t: dict[str, Any]) -> int:
    try:
        return int(t.get("frame_seq") or (t.get("video") or {}).get("frame_seq") or 0)
    except (TypeError, ValueError):
        return 0


def build_event_records(
    session_id: str,
    ticks: list[dict[str, Any]],
    *,
    controller_bodied: bool,
    board_locked: bool,
) -> list[EventRecord]:
    sid = session_id or ""
    rows = [t for t in ticks if isinstance(t, dict)]
    events: list[EventRecord] = []
    n = 1
    if controller_bodied and board_locked:
        for s in samples_from_ticks(rows):
            t0 = int(s.get("input_clock_ns") or 0)
            t1 = int(s.get("outcome_clock_ns") or 0)
            sit = _sit_summary(_sit_at(rows, t1), locked=True)
            events.append(
                EventRecord(
                    session_id=sid,
                    event_id=_eid(sid, n),
                    event_type="press_to_score",
                    t_start_ns=t0,
                    t_end_ns=t1,
                    frame_start=0,
                    frame_end=0,
                    input_summary={"press_clock_ns": t0, "latency_ns": int(s.get("latency_ns") or 0)},
                    situation_summary=sit,
                    evidence={"clip_ids": [s["clip_id"]] if s.get("clip_id") else [], "coach_type": "timing"},
                )
            )
            n += 1
        for w in spam_windows(_presses_from_ticks(rows)):
            events.append(
                EventRecord(
                    session_id=sid,
                    event_id=_eid(sid, n),
                    event_type="spam_window",
                    t_start_ns=int(w.get("t_start_ns") or 0),
                    t_end_ns=int(w.get("t_end_ns") or 0),
                    frame_start=0,
                    frame_end=0,
                    input_summary={"button": w.get("button"), "count": w.get("count")},
                    situation_summary=_sit_summary(_sit_at(rows, int(w.get("t_start_ns") or 0)), locked=True),
                    evidence={"clip_ids": list(w.get("clip_ids") or []), "coach_type": "pattern"},
                )
            )
            n += 1
    if board_locked:
        prev: tuple[Any, Any] | None = None
        prev_yl = None
        for t in sorted(rows, key=lambda x: int(x.get("clock_ns") or 0)):
            if not (t.get("board_locked") or (t.get("situation") or {}).get("board_locked")):
                continue
            sit = t.get("situation") if isinstance(t.get("situation"), dict) else {}
            key = (sit.get("home_score"), sit.get("away_score"))
            yl = sit.get("yard_line")
            clock = int(t.get("clock_ns") or 0)
            fr = _frame(t)
            if prev is not None and (key != prev or yl != prev_yl):
                events.append(
                    EventRecord(
                        session_id=sid,
                        event_id=_eid(sid, n),
                        event_type="situation_shift",
                        t_start_ns=clock,
                        t_end_ns=clock,
                        frame_start=fr,
                        frame_end=fr,
                        input_summary=None,
                        situation_summary=_sit_summary(sit, locked=True),
                        evidence={"clip_ids": [t.get("clip_id")] if t.get("clip_id") else [], "coach_type": "situation"},
                    )
                )
                n += 1
            prev = key
            prev_yl = yl
    events.sort(key=lambda e: (e.t_start_ns, e.event_id))
    for i, ev in enumerate(events, start=1):
        ev.event_id = _eid(sid, i)
    return events


def _lines(events: list[EventRecord], *, bodied: bool, locked: bool) -> list[str]:
    out: list[str] = []
    for e in events:
        if e.event_type == "press_to_score":
            lag = (e.input_summary or {}).get("latency_ns")
            out.append(f"press_to_score latency_ns={lag}")
        elif e.event_type == "spam_window":
            btn = (e.input_summary or {}).get("button") if bodied else None
            cnt = (e.input_summary or {}).get("count")
            out.append(f"spam_window count={cnt}" + (f" button={btn}" if btn else ""))
        elif e.event_type == "situation_shift" and locked:
            sit = e.situation_summary or {}
            bits = []
            if sit.get("home_score") is not None and sit.get("away_score") is not None:
                bits.append(f"{sit.get('home_score')}-{sit.get('away_score')}")
            if sit.get("yard_line") is not None:
                bits.append(f"yl={sit.get('yard_line')}")
            out.append("situation_shift " + (" ".join(str(b) for b in bits) or "locked board changed"))
    return out


def generate_narrative(
    session_id: str = "",
    *,
    ticks: list[dict[str, Any]] | None = None,
    persist: bool = False,
    path: Path | str | None = None,
) -> dict[str, Any]:
    sid = str(session_id or "")
    rows = list(ticks or [])
    if ticks is None:
        try:
            from qoresence.foundry.cer_log import get_cer_log

            rows = get_cer_log().recent(200)
        except Exception:
            rows = []
    bodied = any(
        bool(t.get("controller_bodied") or (t.get("input") or {}).get("bodied")) for t in rows
    )
    locked = any(
        bool(t.get("board_locked") or (t.get("situation") or {}).get("board_locked")) for t in rows
    )
    recs = build_event_records(sid, rows, controller_bodied=bodied, board_locked=locked)
    payload = {
        "schema_version": NARRATIVE_SCHEMA,
        "session_id": sid,
        "controller_bodied": bool(bodied),
        "board_locked": bool(locked),
        "event_schema": EVENT_SCHEMA,
        "events": [e.to_dict() for e in recs],
        "text": " ".join(_lines(recs, bodied=bodied, locked=locked)),
        "plane": "qoresence-observation",
        "read_only": True,
    }
    with _lock:
        _last[sid or "_"] = payload
    if persist:
        try:
            out = Path(path) if path is not None else Path("logs") / "civif" / f"narrative_{sid or 'session'}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, default=str), encoding="utf-8")
            payload["path"] = str(out)
        except Exception as e:
            log.debug("narrative persist: %s", e)
    return payload


class NarrativeEngine:
    def generate(self, **kwargs: Any) -> dict[str, Any]:
        return generate_narrative(**kwargs)


def maybe_write_after_coaches(
    session_id: str,
    *,
    ticks: list[dict[str, Any]] | None = None,
    path: Path | str | None = None,
) -> None:
    try:
        generate_narrative(
            session_id,
            ticks=ticks,
            persist=_log_enabled(),
            path=path,
        )
    except Exception as e:
        log.debug("narrative after coaches: %s", e)
