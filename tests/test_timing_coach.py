"""TimingCoach — fail-closed input→outcome latency (coach-1)."""

from __future__ import annotations

from qoresence.core.civif_tick import CoachingReport
from qoresence.core.types import CoachingReport as TypesCoachingReport
from qoresence.foundry.timing_coach import (
    generate_timing_report,
    last_timing_report,
    samples_from_ticks,
)
from qoresence.mcp.server import TOOL_DEFS


def _tick(clock: int, *, bodied: bool, locked: bool, presses: list[tuple[str, int]] | None = None, home=None, away=None):
    events = [{"button": n, "edge_type": "press", "clock_ns": ns} for n, ns in (presses or [])]
    sit = {
        "board_locked": locked,
        "home_score": home if locked else None,
        "away_score": away if locked else None,
    }
    return {
        "session_id": "sess-t",
        "clock_ns": clock,
        "controller_bodied": bodied,
        "board_locked": locked,
        "input_ticks": events if bodied else [],
        "situation": sit,
    }


def test_schema_is_coach_1_dataclass_not_mcp():
    assert CoachingReport is TypesCoachingReport
    r = CoachingReport(session_id="x")
    d = r.to_dict()
    assert d["schema_version"] == "coach-1"
    assert d["coach_type"] == "timing"
    names = {t["name"] for t in TOOL_DEFS}
    assert "civif_coaching_report" not in names


def test_unbodied_session_has_no_timing_insights():
    samples = [
        {"latency_ns": 500_000_000, "clip_id": "late_a"},
        {"latency_ns": 600_000_000, "clip_id": "late_b"},
    ]
    rep = generate_timing_report(
        "s-unbodied",
        samples=samples,
        controller_bodied=False,
        board_locked=True,
        persist=False,
    )
    assert rep.metrics == {}
    assert rep.issues == []
    assert rep.controller_bodied is False
    blob = rep.to_dict()
    assert "late_a" not in str(blob)
    assert "R2" not in str(blob)


def test_unlocked_board_has_no_timing_insights():
    ticks = [
        _tick(10, bodied=True, locked=False, presses=[("R2", 9)], home=99, away=1),
        _tick(20, bodied=True, locked=False, presses=[], home=100, away=1),
    ]
    rep = generate_timing_report("s-unlock", ticks=ticks, persist=False)
    assert rep.board_locked is False
    assert rep.metrics == {}
    assert rep.issues == []


def test_bodied_locked_metrics_and_late_issue():
    samples = [
        {"latency_ns": 80_000_000, "clip_id": "ok1"},
        {"latency_ns": 100_000_000, "clip_id": "ok2"},
        {"latency_ns": 120_000_000, "clip_id": "ok3"},
        {"latency_ns": 500_000_000, "clip_id": "late_mid"},
        {"latency_ns": 800_000_000, "clip_id": "late_hi"},
    ]
    rep = generate_timing_report("s-late", samples=samples, persist=False)
    m = rep.metrics
    assert m["latency_samples"] == 5
    assert m["median_latency_ns"] == 120_000_000
    assert m["late_input_rate"] == 0.4
    assert len(rep.issues) == 1
    assert rep.issues[0]["type"] == "late_input"
    assert rep.issues[0]["clip_ids"][0] == "late_hi"
    assert "late_mid" in rep.issues[0]["clip_ids"]
    stored = last_timing_report("s-late")
    assert stored is not None
    assert stored.metrics["latency_samples"] == 5


def test_samples_from_ticks_pairs_press_with_score_change():
    ticks = [
        _tick(1_000, bodied=True, locked=True, home=7, away=0),
        _tick(1_100, bodied=True, locked=True, presses=[("R2", 1_050)], home=7, away=0),
        _tick(1_500, bodied=True, locked=True, home=14, away=0),
    ]
    rows = samples_from_ticks(ticks)
    assert len(rows) == 1
    assert rows[0]["latency_ns"] == 1_500 - 1_050


def test_unbodied_ticks_do_not_form_samples():
    ticks = [
        _tick(1_000, bodied=False, locked=True, presses=[("R2", 1_000)], home=0, away=0),
        _tick(2_000, bodied=False, locked=True, home=7, away=0),
    ]
    assert samples_from_ticks(ticks) == []
    rep = generate_timing_report("s", ticks=ticks, persist=False)
    assert rep.metrics == {}
