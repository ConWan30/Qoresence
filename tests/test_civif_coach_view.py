"""CIVIF /civif.html TimingCoach operator view — JSON contract."""

from __future__ import annotations

from pathlib import Path

from qoresence.foundry.pattern_coach import generate_pattern_report
from qoresence.foundry.situation_coach import generate_situation_report
from qoresence.foundry.timing_coach import generate_timing_report
from qoresence.mcp.server import handle_civif_live

CIVIF_HTML = Path(__file__).resolve().parents[1] / "qoresence" / "deck" / "civif.html"


def test_civif_html_has_timing_coach_panel():
    blob = CIVIF_HTML.read_text(encoding="utf-8")
    assert "Coach" in blob
    assert 'name="coach-kind"' in blob
    assert "insights unavailable (no report yet)." in blob
    assert "controller not bodied or board unlocked" in blob
    assert "median_latency_ms" in blob
    assert "spam_windows_count" in blob
    assert 'value="situation"' in blob
    assert "median_latency_ns_red_zone" in blob
    assert "/media/clips/" in blob


def test_live_json_coaching_report_key_present():
    out = handle_civif_live()
    assert out["ok"] is True
    assert "coaching_report" in out
    assert "coaching_reports" in out
    assert isinstance(out["coaching_reports"], list)


def test_live_json_unbodied_report_empty_metrics():
    generate_timing_report(
        "view-unbodied",
        samples=[{"latency_ns": 500_000_000, "clip_id": "x"}],
        controller_bodied=False,
        board_locked=True,
        persist=False,
    )
    out = handle_civif_live()
    rep = out["coaching_report"]
    assert rep is not None
    assert rep["controller_bodied"] is False
    assert rep["metrics"] == {}
    assert rep["issues"] == []


def test_live_json_bodied_locked_shows_metrics():
    generate_timing_report(
        "view-ok",
        samples=[
            {"latency_ns": 80_000_000, "clip_id": "ok1"},
            {"latency_ns": 100_000_000, "clip_id": "ok2"},
            {"latency_ns": 120_000_000, "clip_id": "ok3"},
            {"latency_ns": 500_000_000, "clip_id": "late_mid"},
            {"latency_ns": 800_000_000, "clip_id": "late_hi"},
        ],
        persist=False,
    )
    out = handle_civif_live()
    rep = out["coaching_report"]
    assert rep["controller_bodied"] is True
    assert rep["board_locked"] is True
    assert rep["coach_type"] == "timing"
    assert rep["metrics"]["latency_samples"] == 5
    assert rep["issues"][0]["clip_ids"][0] == "late_hi"
    types = {r["coach_type"] for r in out["coaching_reports"]}
    assert "timing" in types


def test_live_json_includes_pattern_in_reports_list():
    generate_pattern_report(
        "view-pat",
        events=[(i * 10_000_000, "square", "press", "c1") for i in range(20)],
        persist=False,
    )
    out = handle_civif_live()
    types = {r["coach_type"] for r in out["coaching_reports"]}
    assert "pattern" in types
    pat = next(r for r in out["coaching_reports"] if r["coach_type"] == "pattern")
    assert pat["metrics"]["spam_windows_count"] >= 1
    assert out["coaching_report"] is None or out["coaching_report"].get("coach_type") == "timing"


def test_live_json_includes_situation_in_reports_list():
    ticks = [
        {
            "clock_ns": 10,
            "controller_bodied": True,
            "board_locked": True,
            "input_ticks": [],
            "situation": {"board_locked": True, "home_score": 0, "away_score": 0, "yard_line": 50},
        }
    ]
    generate_situation_report("view-sit", ticks=ticks, persist=False)
    out = handle_civif_live()
    types = {r["coach_type"] for r in out["coaching_reports"]}
    assert "situation" in types
