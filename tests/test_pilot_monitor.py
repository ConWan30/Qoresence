"""Pilot monitor — freeze/score-delta/closeout fixtures. No hardware."""

from __future__ import annotations

import json
from pathlib import Path

from qoresence.pilot import closeout, metrics
from qoresence.pilot.monitor import PilotMonitor, _get_json


def test_freeze_consecutive_age():
    s = 0
    s = metrics.freeze_streak(True, 6.0, s)
    s = metrics.freeze_streak(True, 6.1, s)
    assert metrics.freeze_flag(s) is False
    s = metrics.freeze_streak(True, 7.0, s)
    assert metrics.freeze_flag(s) is True
    s = metrics.freeze_streak(True, 0.1, s)
    assert s == 0
    assert metrics.freeze_flag(s) is False


def test_classify_freeze_three_kinds():
    assert (
        metrics.classify_freeze(
            has_frame=True, age_s=8.0, frames=100, prev_frames=100
        )
        == "card_stall"
    )
    assert (
        metrics.classify_freeze(
            has_frame=True, age_s=0.2, frames=200, prev_frames=180, graph_stall=True
        )
        == "graph_stall"
    )
    assert metrics.classify_freeze(deck_down=True, has_frame=False) == "deck_lock"
    assert metrics.classify_freeze(has_frame=True, age_s=0.1) == "unknown"


def test_score_delta_and_decrease():
    assert metrics.score_changed((14, 7), (21, 7)) is True
    assert metrics.score_decreased((14, 7), (21, 7)) is False
    assert metrics.score_decreased((17, 21), (10, 7)) is True
    assert metrics.score_changed(None, (0, 0)) is False


def test_closeout_from_fixture_jsonl(tmp_path: Path):
    lines = []
    for i in range(8):
        lines.append(
            {
                "ts": f"2026-08-14T20:00:{i:02d}Z",
                "clock_ns": i * 2_000_000_000,
                "video_age_s": 0.1,
                "frames": 100 + i,
                "has_frame": True,
                "score_home": 7,
                "score_away": 0,
                "score_vlm_locked": True,
                "flags": [],
                "clips_n": 0,
                "society_receipts": 0,
            }
        )
    lines.append(
        {
            "ts": "2026-08-14T20:00:16Z",
            "clock_ns": 16_000_000_000,
            "video_age_s": 6.2,
            "frames": 108,
            "has_frame": True,
            "score_home": 7,
            "score_away": 0,
            "score_vlm_locked": True,
            "flags": ["FREEZE"],
            "clips_n": 0,
        }
    )
    lines.append(
        {
            "ts": "2026-08-14T20:00:18Z",
            "clock_ns": 18_000_000_000,
            "video_age_s": 0.1,
            "frames": 110,
            "has_frame": True,
            "score_home": 14,
            "score_away": 0,
            "score_prev": [7, 0],
            "score_vlm_locked": True,
            "flags": ["SCORE_DELTA"],
            "new_clips": ["clips/hdmi_clip_demo.mp4"],
            "clips_n": 1,
            "society_receipts": 4,
        }
    )
    p = tmp_path / "session_fixture.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    j, md, summary = closeout.write_closeout(p)
    assert j.is_file()
    assert md.is_file()
    assert summary["freeze_events"] >= 1
    assert summary["score_deltas"] >= 1
    assert summary["new_clips"] == 1
    text = md.read_text(encoding="utf-8")
    assert "Capture stability" in text
    assert "Score lock" in text
    assert "score_lock_timeline" in summary
    assert "climax_chapters" in summary
    assert "freeze_classified" in summary
    assert "summary_metrics" in summary
    assert summary["summary_metrics"]["freeze_events"] == summary["freeze_events"]
    assert any(r.get("kind") for r in summary["freeze_classified"])
    assert "## Score lock timeline" in text
    assert "## Climax chapters" in text
    assert "## FREEZE classified" in text
    plays = [c for c in summary["climax_chapters"] if c.get("label") == "touchdown"]
    assert plays, "7→14 should rank as touchdown"
    assert plays[0]["climax_score"] >= 0.9


def test_deck_down_no_raise(tmp_path: Path):
    body, err, dt = _get_json("http://127.0.0.1:59999/health", 0.2)
    assert body is None
    assert err
    assert dt >= 0
    mon = PilotMonitor(
        "http://127.0.0.1:59999",
        interval_s=0.05,
        out_dir=tmp_path,
        clips_dir=tmp_path,
        warm_up_s=0,
        duration_s=0.12,
    )
    mon.start()
    if mon._thread:
        mon._thread.join(timeout=2.0)
    mon.stop(timeout_s=1.0)
    text = mon.session_path.read_text(encoding="utf-8")
    assert "DECK_DOWN" in text
