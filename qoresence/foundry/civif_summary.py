"""CIVIF session summary JSONL — observation only, no UI.

Gated by ``QORESENCE_CIVIF_SUMMARY_LOG=1``. One line per session when at least
one CoachingReport exists. No bus emit.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from qoresence.core.civif_tick import CoachingReport

log = logging.getLogger(__name__)

DEFAULT_PATH = Path("logs") / "civif" / "session_summary.jsonl"


def summary_log_enabled() -> bool:
    return os.getenv("QORESENCE_CIVIF_SUMMARY_LOG", "").strip().lower() in {"1", "true", "on"}


def _frac(n: int, d: int) -> float:
    if d <= 0:
        return 0.0
    return max(0.0, min(1.0, n / d))


def _tick_fractions(ticks: list[dict[str, Any]] | None) -> tuple[float, float]:
    rows = [t for t in (ticks or []) if isinstance(t, dict)]
    if not rows:
        return 0.0, 0.0
    locked = sum(
        1
        for t in rows
        if t.get("board_locked") or (t.get("situation") or {}).get("board_locked")
    )
    bodied = sum(
        1
        for t in rows
        if t.get("controller_bodied") or (t.get("input") or {}).get("bodied")
    )
    n = len(rows)
    return _frac(locked, n), _frac(bodied, n)


def build_summary_line(
    session_id: str,
    *,
    ticks: list[dict[str, Any]] | None = None,
    reports: list[CoachingReport | dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    for r in reports or []:
        if isinstance(r, CoachingReport):
            rows.append(r.to_dict())
        elif isinstance(r, dict) and r.get("coach_type"):
            rows.append(r)
    if not rows:
        return None
    locked_f, bodied_f = _tick_fractions(ticks)
    if ticks is None and not locked_f and not bodied_f:
        try:
            from qoresence.foundry.civif_metrics import snapshot

            snap = snapshot(session_id or "_")
            locked_f = float(snap.get("board_locked_rate") or 0.0)
            if snap.get("controller_bodied_any"):
                bodied_f = 1.0
        except Exception:
            pass
    line: dict[str, Any] = {
        "session_id": session_id or "",
        "board_locked_fraction": locked_f,
        "controller_bodied_fraction": bodied_f,
    }
    by = {str(r.get("coach_type") or ""): r for r in rows}
    if "timing" in by:
        line["timing_coach_present"] = True
        m = by["timing"].get("metrics") or {}
        if m.get("median_latency_ns") is not None:
            line["timing_median_latency_ns"] = m["median_latency_ns"]
        if m.get("late_input_rate") is not None:
            line["timing_late_input_rate"] = m["late_input_rate"]
    if "pattern" in by:
        line["pattern_coach_present"] = True
        m = by["pattern"].get("metrics") or {}
        if m.get("spam_windows_count") is not None:
            line["pattern_spam_windows_count"] = m["spam_windows_count"]
        if m.get("mistimed_combo_count") is not None:
            line["pattern_mistimed_combo_count"] = m["mistimed_combo_count"]
    if "situation" in by:
        line["situation_coach_present"] = True
    return line


def write_session_summary(
    session_id: str = "",
    *,
    ticks: list[dict[str, Any]] | None = None,
    reports: list[Any] | None = None,
    path: Path | str | None = None,
) -> Path | None:
    if not summary_log_enabled():
        return None
    line = build_summary_line(session_id, ticks=ticks, reports=reports)
    if line is None:
        return None
    out = Path(path) if path is not None else DEFAULT_PATH
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, default=str) + "\n")
    except Exception as e:
        log.debug("civif summary jsonl: %s", e)
        return None
    return out


def maybe_write_after_coaches(session_id: str) -> None:
    """Best-effort; never raises. Call after Timing/Pattern/Situation generate."""
    try:
        from qoresence.foundry.cer_log import get_cer_log
        from qoresence.foundry.pattern_coach import last_pattern_report
        from qoresence.foundry.timing_coach import last_timing_report

        reports: list[Any] = []
        t = last_timing_report(session_id) or last_timing_report()
        p = last_pattern_report(session_id) or last_pattern_report()
        if t is not None:
            reports.append(t)
        if p is not None:
            reports.append(p)
        try:
            from qoresence.foundry.situation_coach import last_situation_report

            s = last_situation_report(session_id) or last_situation_report()
            if s is not None:
                reports.append(s)
        except Exception:
            pass
        ticks = get_cer_log().recent(200)
        write_session_summary(session_id, ticks=ticks, reports=reports)
    except Exception as e:
        log.debug("civif summary after coaches: %s", e)
