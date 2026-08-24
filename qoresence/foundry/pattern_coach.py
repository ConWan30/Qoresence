"""PatternCoach — observational HID patterns, fail-closed.

``coach_type: pattern``. No bus emit. Not listed in MCP tools/list.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

from qoresence.core.civif_tick import COACH_SCHEMA, CoachingReport
from qoresence.core.types import clock_ns

log = logging.getLogger(__name__)

SPAM_WINDOW_NS = 2_000_000_000
SPAM_PRESS_GT = 8
SPAM_ISSUE_MIN = 3
COMBO_MIN_NS = 40_000_000
COMBO_MAX_NS = 350_000_000
COMBO_LOOKAHEAD_NS = 1_000_000_000
COMBO_ISSUE_MIN = 5
STICK_NAMES = frozenset({"l3", "r3", "stick", "left", "right", "lx", "ly", "rx", "ry"})
R2_NAMES = frozenset({"r2"})

_lock = threading.Lock()
_last: dict[str, CoachingReport] = {}


def last_pattern_report(session_id: str = "") -> CoachingReport | None:
    with _lock:
        if session_id:
            return _last.get(str(session_id))
        if not _last:
            return None
        return next(reversed(_last.values()))


def _coach_log_enabled() -> bool:
    return os.getenv("QORESENCE_CIVIF_COACH_LOG", "").strip().lower() in {"1", "true", "on"}


def _presses_from_ticks(ticks: list[dict[str, Any]]) -> list[tuple[int, str, str, str]]:
    """(clock_ns, button_lower, kind, clip_id) for bodied+locked ticks only."""
    out: list[tuple[int, str, str, str]] = []
    for t in ticks or []:
        if not isinstance(t, dict):
            continue
        bodied = bool(t.get("controller_bodied") or (t.get("input") or {}).get("bodied"))
        locked = bool(t.get("board_locked") or (t.get("situation") or {}).get("board_locked"))
        if not bodied or not locked:
            continue
        cid = str(t.get("clip_id") or "")
        events = t.get("input_ticks") or (t.get("input") or {}).get("events") or []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            name = str(ev.get("button") or ev.get("name") or "").strip().lower()
            if not name:
                continue
            kind = str(ev.get("edge_type") or ev.get("kind") or "").lower()
            ns = int(ev.get("clock_ns") or t.get("clock_ns") or 0)
            if ns <= 0:
                continue
            out.append((ns, name, kind, cid))
    out.sort(key=lambda r: r[0])
    return out


def _presses_from_sidecars(clips_dir: Path) -> list[tuple[int, str, str, str]]:
    if not clips_dir.is_dir():
        return []
    from qoresence.core.coupled_event import event_clock_ns, input_events

    out: list[tuple[int, str, str, str]] = []
    for path in clips_dir.glob("*.coupling.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        inp = data.get("input") if isinstance(data.get("input"), dict) else {}
        sit = data.get("situation") if isinstance(data.get("situation"), dict) else {}
        if not inp.get("bodied") or not sit.get("board_locked"):
            continue
        stem = path.name[: -len(".coupling.json")]
        for ev in input_events(data):
            name = str(ev.get("button") or ev.get("name") or "").strip().lower()
            if not name:
                continue
            kind = str(ev.get("edge_type") or ev.get("kind") or "").lower()
            ns = event_clock_ns(ev)
            if ns <= 0:
                continue
            out.append((ns, name, kind, stem))
    out.sort(key=lambda r: r[0])
    return out


def spam_windows(
    events: list[tuple[int, str, str, str]],
    *,
    window_ns: int = SPAM_WINDOW_NS,
    press_gt: int = SPAM_PRESS_GT,
) -> list[dict[str, Any]]:
    by_btn: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for ns, name, kind, cid in events:
        if kind in {"release", "move"}:
            continue
        if kind in {"press", "trigger", ""}:
            by_btn[name].append((ns, cid))
    found: list[dict[str, Any]] = []
    for name, items in by_btn.items():
        i = 0
        while i < len(items):
            j = i
            clips: list[str] = []
            while j < len(items) and items[j][0] - items[i][0] <= window_ns:
                if items[j][1] and items[j][1] not in clips:
                    clips.append(items[j][1])
                j += 1
            count = j - i
            if count > press_gt:
                found.append(
                    {
                        "button": name,
                        "count": count,
                        "t_start_ns": items[i][0],
                        "t_end_ns": items[j - 1][0],
                        "clip_ids": clips,
                    }
                )
                i = j
            else:
                i += 1
    return found


def mistimed_combos(events: list[tuple[int, str, str, str]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for i, (ns, name, kind, cid) in enumerate(events):
        stickish = name in STICK_NAMES or kind == "move"
        if not stickish:
            continue
        for ns2, name2, kind2, cid2 in events[i + 1 :]:
            if ns2 - ns > COMBO_LOOKAHEAD_NS:
                break
            if name2 not in R2_NAMES:
                continue
            if kind2 in {"release"}:
                continue
            lag = ns2 - ns
            if lag < COMBO_MIN_NS or lag > COMBO_MAX_NS:
                clips = [c for c in (cid, cid2) if c]
                found.append(
                    {
                        "buttons": [name, name2],
                        "latency_ns": lag,
                        "t_start_ns": ns,
                        "t_end_ns": ns2,
                        "clip_ids": clips,
                    }
                )
            break
    return found


def _empty(session_id: str, *, bodied: bool, locked: bool, why: str) -> CoachingReport:
    return CoachingReport(
        session_id=session_id or "",
        schema_version=COACH_SCHEMA,
        coach_type="pattern",
        metrics={},
        issues=[],
        controller_bodied=bodied,
        board_locked=locked,
        generated_at_ns=clock_ns(),
        recommendations=[why],
    )


def generate_pattern_report(
    session_id: str = "",
    *,
    ticks: list[dict[str, Any]] | None = None,
    clips_dir: Path | str | None = None,
    events: list[tuple[int, str, str, str]] | None = None,
    controller_bodied: bool | None = None,
    board_locked: bool | None = None,
    persist: bool = False,
    bodied_play_ns: int | None = None,
) -> CoachingReport:
    sid = str(session_id or "")
    tick_rows = list(ticks or [])
    if ticks is None and events is None:
        try:
            from qoresence.foundry.cer_log import get_cer_log

            tick_rows = get_cer_log().recent(200)
        except Exception:
            tick_rows = []
    if events is not None:
        if controller_bodied is None:
            controller_bodied = True
        if board_locked is None:
            board_locked = True
    if controller_bodied is None:
        controller_bodied = any(
            bool(t.get("controller_bodied") or (t.get("input") or {}).get("bodied"))
            for t in tick_rows
        )
    if board_locked is None:
        board_locked = any(
            bool(t.get("board_locked") or (t.get("situation") or {}).get("board_locked"))
            for t in tick_rows
        )
    if not controller_bodied or not board_locked:
        why = "pattern_withheld_unbodied" if not controller_bodied else "pattern_withheld_board_unlocked"
        rep = _empty(sid, bodied=bool(controller_bodied), locked=bool(board_locked), why=why)
        _store(rep, persist=persist)
        return rep

    seq = list(events) if events is not None else _presses_from_ticks(tick_rows)
    if events is None and clips_dir is not None:
        seq.extend(_presses_from_sidecars(Path(clips_dir)))
    spam = spam_windows(seq)
    mist = mistimed_combos(seq)
    span = 0
    if seq:
        span = max(1, seq[-1][0] - seq[0][0])
    if bodied_play_ns is not None:
        span = max(1, int(bodied_play_ns))
    minutes = span / 60e9
    metrics = {
        "spam_windows_count": len(spam),
        "mistimed_combo_count": len(mist),
        "spam_rate": (len(spam) / minutes) if minutes else float(len(spam)),
    }
    issues: list[dict[str, Any]] = []
    if len(spam) >= SPAM_ISSUE_MIN:
        clips: list[str] = []
        for w in spam:
            for c in w.get("clip_ids") or []:
                if c not in clips:
                    clips.append(c)
            if len(clips) >= 5:
                break
        btn = spam[0].get("button") or "button"
        issues.append(
            {
                "type": "button_spam",
                "description": (
                    f"Observed {len(spam)} short windows with more than {SPAM_PRESS_GT} "
                    f"presses of the same button ({btn}) while DualSense was bodied "
                    "and the scoreboard was locked."
                ),
                "clip_ids": clips,
            }
        )
    if len(mist) >= COMBO_ISSUE_MIN:
        clips = []
        for w in mist:
            for c in w.get("clip_ids") or []:
                if c not in clips:
                    clips.append(c)
            if len(clips) >= 5:
                break
        issues.append(
            {
                "type": "mistimed_combo",
                "description": (
                    f"Observed {len(mist)} stick-then-R2 pairs whose gap was outside "
                    f"{COMBO_MIN_NS / 1e6:.0f}–{COMBO_MAX_NS / 1e6:.0f} ms "
                    "(bodied pad, locked board)."
                ),
                "clip_ids": clips,
            }
        )
    rep = CoachingReport(
        session_id=sid,
        schema_version=COACH_SCHEMA,
        coach_type="pattern",
        metrics=metrics,
        issues=issues,
        controller_bodied=True,
        board_locked=True,
        generated_at_ns=clock_ns(),
        timing_stats=metrics,
        linked_clip_ids=list(issues[0].get("clip_ids") or []) if issues else [],
    )
    _store(rep, persist=persist)
    return rep


def _store(rep: CoachingReport, *, persist: bool) -> None:
    with _lock:
        _last[rep.session_id or "_"] = rep
    if not persist:
        return
    try:
        sid = rep.session_id or os.getenv("QORESENCE_SESSION_ID") or "session"
        path = Path("logs") / "civif" / f"coaching_{sid}_pattern.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rep.to_dict(), default=str), encoding="utf-8")
    except Exception as e:
        log.debug("pattern coach persist: %s", e)


class PatternCoach:
    def generate(self, **kwargs: Any) -> CoachingReport:
        return generate_pattern_report(**kwargs)
