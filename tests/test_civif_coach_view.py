"""CIVIF /civif.html TimingCoach operator view — JSON contract."""

from __future__ import annotations

from pathlib import Path

from qoresence.foundry.timing_coach import generate_timing_report
from qoresence.mcp.server import handle_civif_live

CIVIF_HTML = Path(__file__).resolve().parents[1] / "qoresence" / "deck" / "civif.html"


def test_civif_html_has_timing_coach_panel():
    blob = CIVIF_HTML.read_text(encoding="utf-8")
    assert "Coach (Timing)" in blob
    assert "Timing insights unavailable (no report yet)." in blob
    assert "controller not bodied or board unlocked" in blob
    assert "median_latency_ms" in blob
    assert "late_input_rate" in blob
    assert "/media/clips/" in blob


def test_live_json_coaching_report_key_present():
    out = handle_civif_live()
    assert out["ok"] is True
    assert "coaching_report" in out


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
