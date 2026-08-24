"""Session summary JSONL — env-gated, coach-present only."""

from __future__ import annotations

from qoresence.core.civif_tick import CoachingReport
from qoresence.foundry.civif_summary import build_summary_line, write_session_summary


def test_no_line_without_coaches(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_CIVIF_SUMMARY_LOG", "1")
    p = tmp_path / "session_summary.jsonl"
    out = write_session_summary("s", ticks=[{"board_locked": True}], reports=[], path=p)
    assert out is None
    assert not p.exists()


def test_no_write_when_env_off(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_CIVIF_SUMMARY_LOG", raising=False)
    p = tmp_path / "session_summary.jsonl"
    rep = CoachingReport(session_id="s", coach_type="timing")
    assert write_session_summary("s", reports=[rep], path=p) is None
    assert not p.exists()


def test_writes_line_when_coach_present(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_CIVIF_SUMMARY_LOG", "1")
    p = tmp_path / "session_summary.jsonl"
    ticks = [
        {"board_locked": True, "controller_bodied": True},
        {"board_locked": False, "controller_bodied": True},
    ]
    timing = CoachingReport(
        session_id="s1",
        coach_type="timing",
        metrics={"median_latency_ns": 312000000, "late_input_rate": 0.21},
        controller_bodied=True,
        board_locked=True,
    )
    path = write_session_summary("s1", ticks=ticks, reports=[timing], path=p)
    assert path == p
    line = build_summary_line("s1", ticks=ticks, reports=[timing])
    assert line is not None
    assert line["session_id"] == "s1"
    assert line["board_locked_fraction"] == 0.5
    assert line["controller_bodied_fraction"] == 1.0
    assert line["timing_coach_present"] is True
    assert line["timing_median_latency_ns"] == 312000000
    assert line["timing_late_input_rate"] == 0.21
    assert "pattern_coach_present" not in line
    assert "pattern_spam_windows_count" not in line
    blob = p.read_text(encoding="utf-8").strip()
    assert "timing_coach_present" in blob


def test_fail_closed_coach_still_summarizes(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_CIVIF_SUMMARY_LOG", "1")
    p = tmp_path / "s.jsonl"
    ticks = [{"board_locked": False, "controller_bodied": False}]
    pat = CoachingReport(
        session_id="fc",
        coach_type="pattern",
        metrics={},
        issues=[],
        controller_bodied=False,
        board_locked=False,
    )
    write_session_summary("fc", ticks=ticks, reports=[pat], path=p)
    line = build_summary_line("fc", ticks=ticks, reports=[pat])
    assert line is not None
    assert line["pattern_coach_present"] is True
    assert "pattern_spam_windows_count" not in line
    assert line["board_locked_fraction"] == 0.0
    assert line["controller_bodied_fraction"] == 0.0
