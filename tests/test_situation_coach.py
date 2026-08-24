"""SituationCoach — fail-closed situation splits."""

from __future__ import annotations

from qoresence.foundry.situation_coach import generate_situation_report
from qoresence.mcp.server import TOOL_DEFS


def _tick(clock, *, yard=None, clutch=None, home=0, away=0, presses=None, clip=""):
    sit = {
        "board_locked": True,
        "home_score": home,
        "away_score": away,
        "yard_line": yard,
        "clutch_score": clutch,
    }
    ev = [{"button": n, "edge_type": "press", "clock_ns": ns} for n, ns in (presses or [])]
    return {
        "clock_ns": clock,
        "controller_bodied": True,
        "board_locked": True,
        "clip_id": clip,
        "input_ticks": ev,
        "situation": sit,
    }


def test_not_in_mcp():
    assert "civif_coaching_report" not in {t["name"] for t in TOOL_DEFS}


def test_unbodied_empty():
    ticks = [_tick(1, yard=10, home=0, presses=[("R2", 1)])]
    ticks[0]["controller_bodied"] = False
    ticks[0]["input_ticks"] = []
    rep = generate_situation_report("s", ticks=ticks, controller_bodied=False, board_locked=True)
    assert rep.coach_type == "situation"
    assert rep.metrics == {}
    assert rep.issues == []


def test_unlocked_empty():
    ticks = [_tick(1, yard=10)]
    ticks[0]["board_locked"] = False
    ticks[0]["situation"]["board_locked"] = False
    rep = generate_situation_report("s", ticks=ticks, controller_bodied=True, board_locked=False)
    assert rep.metrics == {}
    assert rep.issues == []


def test_red_zone_latency_issue_and_clips():
    ticks = [
        _tick(1_000_000_000, yard=50, home=0, away=0, clip="open"),
        _tick(1_010_000_000, yard=50, home=0, away=0, presses=[("R2", 1_000_000_000)], clip="open"),
        _tick(1_050_000_000, yard=50, home=7, away=0, clip="open"),
        _tick(2_000_000_000, yard=10, home=7, away=0, clip="red"),
        _tick(2_010_000_000, yard=10, home=7, away=0, presses=[("R2", 2_000_000_000)], clip="red"),
        _tick(2_200_000_000, yard=10, home=14, away=0, clip="red"),
    ]
    rep = generate_situation_report("rz", ticks=ticks, persist=False)
    assert rep.metrics["median_latency_ns_non_red_zone"] == 50_000_000
    assert rep.metrics["median_latency_ns_red_zone"] == 200_000_000
    types = {i["type"] for i in rep.issues}
    assert "red_zone_latency" in types
    iss = next(i for i in rep.issues if i["type"] == "red_zone_latency")
    assert "red" in iss["clip_ids"]
