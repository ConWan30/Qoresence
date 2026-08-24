"""TimingCoach — input→outcome latency, fail-closed observation only.

Runs only when DualSense is bodied on this host and the scoreboard is locked.
Does not emit bus events. MCP ``civif_coaching_report`` is not listed yet.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from qoresence.core.civif_tick import COACH_SCHEMA, CoachingReport
from qoresence.core.coupled_event import event_clock_ns, input_events
from qoresence.core.types import clock_ns

log = logging.getLogger(__name__)

LATE_THRESHOLD_NS = 400_000_000  # 400 ms
MIN_ISSUE_SAMPLES = 5
KEY_BUTTONS = frozenset(
    {"r2", "l2", "r1", "l1", "x", "cross", "square", "circle", "triangle", "□", "×"}
)

_lock = threading.Lock()
_last: dict[str, CoachingReport] = {}


def _coach_log_enabled() -> bool:
    return os.getenv("QORESENCE_CIVIF_COACH_LOG", "").strip().lower() in {"1", "true", "on"}


def last_timing_report(session_id: str = "") -> CoachingReport | None:
    with _lock:
        if session_id:
            return _last.get(str(session_id))
        if not _last:
            return None
        return next(reversed(_last.values()))


def _pct(sorted_vals: list[int], p: float) -> int | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = min(len(sorted_vals) - 1, max(0, int(round((len(sorted_vals) - 1) * p))))
    return int(sorted_vals[idx])


def _button_name(ev: dict[str, Any]) -> str:
    return str(ev.get("button") or ev.get("name") or "").strip()


def _is_key_press(ev: dict[str, Any]) -> bool:
    name = _button_name(ev).lower()
    if name not in KEY_BUTTONS:
        return False
    kind = str(ev.get("edge_type") or ev.get("kind") or "").lower()
    if kind in {"press", "trigger"}:
        return True
    if kind in {"release", "move"}:
        return False
    try:
        return float(ev.get("value") or 1.0) > 0.15
    except (TypeError, ValueError):
        return False


def _score_key(sit: dict[str, Any] | None) -> tuple[Any, Any] | None:
    if not isinstance(sit, dict) or not sit.get("board_locked"):
        return None
    h, a = sit.get("home_score"), sit.get("away_score")
    if h is None and a is None:
        return None
    return (h, a)


def samples_from_ticks(ticks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair last key press with the next locked scoreboard digit change."""
    rows = sorted((t for t in ticks if isinstance(t, dict)), key=lambda t: int(t.get("clock_ns") or 0))
    pending_ns: int | None = None
    last_score: tuple[Any, Any] | None = None
    out: list[dict[str, Any]] = []
    for t in rows:
        bodied = bool(t.get("controller_bodied") or (t.get("input") or {}).get("bodied"))
        locked = bool(t.get("board_locked") or (t.get("situation") or {}).get("board_locked"))
        if not bodied or not locked:
            pending_ns = None
            continue
        clock = int(t.get("clock_ns") or 0)
        events = t.get("input_ticks") or (t.get("input") or {}).get("events") or []
        for ev in events:
            if isinstance(ev, dict) and _is_key_press(ev):
                ns = int(ev.get("clock_ns") or clock)
                if ns > 0:
                    pending_ns = ns
        sit = t.get("situation") if isinstance(t.get("situation"), dict) else {}
        sk = _score_key(sit)
        if pending_ns and sk is not None and last_score is not None and sk != last_score:
            lag = clock - pending_ns
            if lag > 0:
                out.append(
                    {
                        "latency_ns": lag,
                        "input_clock_ns": pending_ns,
                        "outcome_clock_ns": clock,
                        "clip_id": str(t.get("clip_id") or ""),
                    }
                )
            pending_ns = None
        if sk is not None:
            last_score = sk
    return out


def samples_from_clips(clips_dir: Path | str | None) -> list[dict[str, Any]]:
    """Press in a bodied+locked sidecar → next history score change, else skip."""
    if clips_dir is None:
        return []
    d = Path(clips_dir)
    if not d.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(d.glob("*.coupling.json")):
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
        press_ns = 0
        for ev in input_events(data):
            if _is_key_press(ev):
                ns = event_clock_ns(ev)
                if ns > 0:
                    press_ns = ns
                    break
        if press_ns <= 0:
            continue
        hist = data.get("coupling_history")
        if not isinstance(hist, list):
            civ = data.get("coupling_civif") if isinstance(data.get("coupling_civif"), dict) else {}
            hist = civ.get("history") if isinstance(civ.get("history"), list) else []
        outcome_ns = 0
        base = _score_key(sit)
        for row in hist:
            if not isinstance(row, dict):
                continue
            ns = int(row.get("video_clock_ns") or row.get("clock_ns") or 0)
            if ns <= press_ns:
                continue
            rsit = row.get("situation") if isinstance(row.get("situation"), dict) else {}
            if not rsit:
                rsit = {
                    "board_locked": bool(row.get("board_locked") or sit.get("board_locked")),
                    "home_score": row.get("home_score"),
                    "away_score": row.get("away_score"),
                }
            sk = _score_key(rsit)
            if sk is not None and base is not None and sk != base:
                outcome_ns = ns
                break
        if outcome_ns <= press_ns:
            continue
        out.append(
            {
                "latency_ns": outcome_ns - press_ns,
                "input_clock_ns": press_ns,
                "outcome_clock_ns": outcome_ns,
                "clip_id": stem,
            }
        )
    return out


def _empty_report(
    session_id: str,
    *,
    bodied: bool,
    locked: bool,
    withheld: str,
) -> CoachingReport:
    return CoachingReport(
        session_id=session_id or "",
        schema_version=COACH_SCHEMA,
        coach_type="timing",
        metrics={},
        issues=[],
        controller_bodied=bodied,
        board_locked=locked,
        generated_at_ns=clock_ns(),
        recommendations=[withheld],
    )


def generate_timing_report(
    session_id: str = "",
    *,
    ticks: list[dict[str, Any]] | None = None,
    clips_dir: Path | str | None = None,
    samples: list[dict[str, Any]] | None = None,
    controller_bodied: bool | None = None,
    board_locked: bool | None = None,
    persist: bool = False,
    late_threshold_ns: int = LATE_THRESHOLD_NS,
) -> CoachingReport:
    """Build a coach-1 TimingCoach report. Detailed metrics only if bodied and locked."""
    sid = str(session_id or "")
    tick_rows = list(ticks or [])
    if ticks is None and samples is None:
        try:
            from qoresence.foundry.cer_log import get_cer_log

            tick_rows = get_cer_log().recent(200)
        except Exception:
            tick_rows = []
    if samples is not None:
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
        if clips_dir is not None:
            for p in Path(clips_dir).glob("*.coupling.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                sit = data.get("situation") if isinstance(data, dict) else {}
                inp = data.get("input") if isinstance(data, dict) else {}
                if isinstance(sit, dict) and sit.get("board_locked"):
                    board_locked = True
                if isinstance(inp, dict) and inp.get("bodied"):
                    controller_bodied = True

    if not controller_bodied or not board_locked:
        why = "timing_withheld_unbodied" if not controller_bodied else "timing_withheld_board_unlocked"
        rep = _empty_report(sid, bodied=bool(controller_bodied), locked=bool(board_locked), withheld=why)
        _store(rep, persist=persist)
        return rep

    if samples is not None:
        collected = list(samples)
    else:
        collected = samples_from_ticks(tick_rows)
        collected.extend(samples_from_clips(clips_dir))

    lats = [int(s["latency_ns"]) for s in collected if int(s.get("latency_ns") or 0) > 0]
    lats.sort()
    n = len(lats)
    late_n = sum(1 for x in lats if x > int(late_threshold_ns))
    metrics: dict[str, Any] = {
        "latency_samples": n,
        "median_latency_ns": _pct(lats, 0.5),
        "p75_latency_ns": _pct(lats, 0.75),
        "p90_latency_ns": _pct(lats, 0.90),
        "late_input_rate": (late_n / n) if n else 0.0,
        "late_threshold_ns": int(late_threshold_ns),
    }
    issues: list[dict[str, Any]] = []
    if n >= MIN_ISSUE_SAMPLES and (late_n / n) >= 0.4:
        ranked = sorted(collected, key=lambda s: -int(s.get("latency_ns") or 0))
        clip_ids = []
        for s in ranked:
            cid = str(s.get("clip_id") or "")
            if cid and cid not in clip_ids:
                clip_ids.append(cid)
            if len(clip_ids) >= 5:
                break
        issues.append(
            {
                "type": "late_input",
                "description": (
                    f"{late_n} of {n} observed press-to-scoreboard latencies exceeded "
                    f"{int(late_threshold_ns) / 1e6:.0f} ms (locked board, bodied pad)."
                ),
                "clip_ids": clip_ids,
            }
        )
    rep = CoachingReport(
        session_id=sid,
        schema_version=COACH_SCHEMA,
        coach_type="timing",
        metrics=metrics,
        issues=issues,
        controller_bodied=True,
        board_locked=True,
        generated_at_ns=clock_ns(),
        timing_stats=metrics,
        linked_clip_ids=list((issues[0].get("clip_ids") if issues else []) or []),
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
        path = Path("logs") / "civif" / f"coaching_{sid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rep.to_dict(), default=str), encoding="utf-8")
    except Exception as e:
        log.debug("timing coach persist: %s", e)


class TimingCoach:
    """Small facade used by clip export / pilot closeout."""

    def generate(self, **kwargs: Any) -> CoachingReport:
        return generate_timing_report(**kwargs)


def refresh_after_clip_export(clips_dir: Path | str | None = None) -> None:
    """Best-effort session report after a Foundry MP4+sidecar write. Never raises."""
    try:
        from qoresence.core.session import SessionAuthority

        ident = SessionAuthority.current()
        sid = ident.session_id if ident is not None else ""
    except Exception:
        sid = os.getenv("QORESENCE_SESSION_ID") or ""
    try:
        generate_timing_report(sid, clips_dir=clips_dir, persist=_coach_log_enabled())
    except Exception as e:
        log.debug("timing coach after export: %s", e)
    try:
        from qoresence.foundry.pattern_coach import generate_pattern_report

        generate_pattern_report(sid, clips_dir=clips_dir, persist=_coach_log_enabled())
    except Exception as e:
        log.debug("pattern coach after export: %s", e)
