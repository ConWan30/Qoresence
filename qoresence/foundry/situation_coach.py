"""SituationCoach — compare latency/spam across locked situations.

``coach_type: situation``. Red zone only when yard_line is stamped. Clutch only
when clutch_score is stored. Fail-closed if unbodied or unlocked.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from qoresence.core.civif_tick import COACH_SCHEMA, CoachingReport
from qoresence.core.types import clock_ns
from qoresence.foundry.pattern_coach import _presses_from_ticks, spam_windows
from qoresence.foundry.timing_coach import samples_from_ticks

log = logging.getLogger(__name__)

CLUTCH_MIN = 0.6
RED_YARD = 20
LATENCY_DELTA_NS = 100_000_000
SPAM_RATE_DELTA = 0.1

_lock = threading.Lock()
_last: dict[str, CoachingReport] = {}


def last_situation_report(session_id: str = "") -> CoachingReport | None:
    with _lock:
        if session_id:
            return _last.get(str(session_id))
        if not _last:
            return None
        return next(reversed(_last.values()))


def _coach_log_enabled() -> bool:
    return os.getenv("QORESENCE_CIVIF_COACH_LOG", "").strip().lower() in {"1", "true", "on"}


def _pct(vals: list[int], p: float = 0.5) -> int | None:
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    idx = min(len(s) - 1, max(0, int(round((len(s) - 1) * p))))
    return int(s[idx])


def _sit_at(ticks: list[dict[str, Any]], clock_ns: int) -> dict[str, Any]:
    best: dict[str, Any] = {}
    for t in ticks:
        if not isinstance(t, dict):
            continue
        if int(t.get("clock_ns") or 0) > clock_ns:
            continue
        sit = t.get("situation") if isinstance(t.get("situation"), dict) else {}
        if sit.get("board_locked"):
            best = sit
    return best


def _is_red(sit: dict[str, Any]) -> bool | None:
    raw = sit.get("yard_line")
    if raw is None:
        return None
    try:
        return int(raw) <= RED_YARD
    except (TypeError, ValueError):
        return None


def _is_clutch(sit: dict[str, Any]) -> bool | None:
    raw = sit.get("clutch_score")
    if raw is None:
        return None
    try:
        return float(raw) >= CLUTCH_MIN
    except (TypeError, ValueError):
        return None


def _spam_rate(windows: list[dict[str, Any]], span_ns: int) -> float:
    minutes = max(span_ns, 1) / 60e9
    return len(windows) / minutes


def generate_situation_report(
    session_id: str = "",
    *,
    ticks: list[dict[str, Any]] | None = None,
    clips_dir: Path | str | None = None,
    controller_bodied: bool | None = None,
    board_locked: bool | None = None,
    persist: bool = False,
) -> CoachingReport:
    sid = str(session_id or "")
    tick_rows = list(ticks or [])
    if ticks is None:
        try:
            from qoresence.foundry.cer_log import get_cer_log

            tick_rows = get_cer_log().recent(200)
        except Exception:
            tick_rows = []
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
        why = "situation_withheld_unbodied" if not controller_bodied else "situation_withheld_board_unlocked"
        rep = CoachingReport(
            session_id=sid,
            schema_version=COACH_SCHEMA,
            coach_type="situation",
            metrics={},
            issues=[],
            controller_bodied=bool(controller_bodied),
            board_locked=bool(board_locked),
            generated_at_ns=clock_ns(),
            recommendations=[why],
        )
        _store(rep, persist=persist)
        return rep

    lats = samples_from_ticks(tick_rows)
    tagged_lat: list[tuple[int, dict[str, Any], str]] = []
    for s in lats:
        sit = _sit_at(tick_rows, int(s.get("outcome_clock_ns") or 0))
        tagged_lat.append((int(s["latency_ns"]), sit, str(s.get("clip_id") or "")))

    presses = _presses_from_ticks(tick_rows)
    spam = spam_windows(presses)
    tagged_spam: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for w in spam:
        sit = _sit_at(tick_rows, int(w.get("t_start_ns") or 0))
        tagged_spam.append((w, sit))

    metrics: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []

    red_l = [n for n, sit, _ in tagged_lat if _is_red(sit) is True]
    nred_l = [n for n, sit, _ in tagged_lat if _is_red(sit) is False]
    if red_l and nred_l:
        metrics["median_latency_ns_red_zone"] = _pct(red_l)
        metrics["median_latency_ns_non_red_zone"] = _pct(nred_l)
        d = int(metrics["median_latency_ns_red_zone"] or 0) - int(
            metrics["median_latency_ns_non_red_zone"] or 0
        )
        if abs(d) > LATENCY_DELTA_NS:
            clips = [c for n, sit, c in tagged_lat if c and _is_red(sit) is (d > 0)][:5]
            ms = abs(d) / 1e6
            issues.append(
                {
                    "type": "red_zone_latency",
                    "description": (
                        f"On locked boards with stamped yard_line, median press-to-score "
                        f"latency was {ms:.0f} ms "
                        f"{'higher' if d > 0 else 'lower'} inside the 20 than outside."
                    ),
                    "clip_ids": clips,
                }
            )

    red_s = [w for w, sit in tagged_spam if _is_red(sit) is True]
    nred_s = [w for w, sit in tagged_spam if _is_red(sit) is False]
    if red_s or nred_s:
        span = 1
        clocks = [int(t.get("clock_ns") or 0) for t in tick_rows]
        if clocks:
            span = max(1, max(clocks) - min(c for c in clocks if c > 0) if any(clocks) else 1)
        rz = _spam_rate(red_s, span)
        nr = _spam_rate(nred_s, span)
        if red_s:
            metrics["spam_rate_red_zone"] = rz
        if nred_s:
            metrics["spam_rate_non_red_zone"] = nr
        if red_s and nred_s and abs(rz - nr) > SPAM_RATE_DELTA:
            clips = []
            src = red_s if rz > nr else nred_s
            for w in src:
                for c in w.get("clip_ids") or []:
                    if c not in clips:
                        clips.append(c)
                if len(clips) >= 5:
                    break
            issues.append(
                {
                    "type": "red_zone_spam",
                    "description": (
                        "Same-button spam windows were more frequent "
                        f"{'inside' if rz > nr else 'outside'} the stamped 20 "
                        "(locked board, bodied pad)."
                    ),
                    "clip_ids": clips,
                }
            )

    cl_l = [n for n, sit, _ in tagged_lat if _is_clutch(sit) is True]
    ncl_l = [n for n, sit, _ in tagged_lat if _is_clutch(sit) is False]
    if cl_l and ncl_l:
        metrics["median_latency_ns_clutch"] = _pct(cl_l)
        metrics["median_latency_ns_non_clutch"] = _pct(ncl_l)
        d = int(metrics["median_latency_ns_clutch"] or 0) - int(
            metrics["median_latency_ns_non_clutch"] or 0
        )
        if abs(d) > LATENCY_DELTA_NS:
            clips = [c for n, sit, c in tagged_lat if c and _is_clutch(sit) is (d > 0)][:5]
            issues.append(
                {
                    "type": "clutch_latency",
                    "description": (
                        f"When stored clutch_score was >= {CLUTCH_MIN}, median "
                        f"press-to-score latency differed by {abs(d) / 1e6:.0f} ms."
                    ),
                    "clip_ids": clips,
                }
            )

    cl_s = [w for w, sit in tagged_spam if _is_clutch(sit) is True]
    ncl_s = [w for w, sit in tagged_spam if _is_clutch(sit) is False]
    if cl_s and ncl_s:
        clocks = [int(t.get("clock_ns") or 0) for t in tick_rows]
        span = max(1, max(clocks) - min(clocks)) if clocks else 1
        cz = _spam_rate(cl_s, span)
        nz = _spam_rate(ncl_s, span)
        metrics["spam_rate_clutch"] = cz
        metrics["spam_rate_non_clutch"] = nz
        if abs(cz - nz) > SPAM_RATE_DELTA:
            issues.append(
                {
                    "type": "clutch_spam",
                    "description": (
                        "Same-button spam windows differed between stored clutch "
                        f"(clutch_score >= {CLUTCH_MIN}) and other locked ticks."
                    ),
                    "clip_ids": [],
                }
            )

    _ = clips_dir
    rep = CoachingReport(
        session_id=sid,
        schema_version=COACH_SCHEMA,
        coach_type="situation",
        metrics=metrics,
        issues=issues,
        controller_bodied=True,
        board_locked=True,
        generated_at_ns=clock_ns(),
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
        path = Path("logs") / "civif" / f"coaching_{sid}_situation.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rep.to_dict(), default=str), encoding="utf-8")
    except Exception as e:
        log.debug("situation coach persist: %s", e)


class SituationCoach:
    def generate(self, **kwargs: Any) -> CoachingReport:
        return generate_situation_report(**kwargs)
