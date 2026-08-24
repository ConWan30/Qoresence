"""CIVIF Layer 2 coaches — fail closed without DualSense on this host."""

from __future__ import annotations

import json

from qoresence.core.coupled_event import build_coupling_sidecar
from qoresence.foundry.coach import coach_clip, coach_from_sidecar, resolve_coupling_file


def _side(**kw):
    base = {
        "clip_id": "hdmi_c",
        "session_id": "",
        "start_ns": 1_000_000_000,
        "end_ns": 2_000_000_000,
        "frame_start": 1,
        "frame_end": 2,
        "video_path": "hdmi_c.mp4",
        "events": [],
        "coupling": {},
        "coupling_history": [],
    }
    base.update(kw)
    return build_coupling_sidecar(**base)


def test_unbodied_withholds_timing_and_pattern():
    out = coach_from_sidecar(_side())
    assert out["ok"] is True
    assert out["bodied"] is False
    assert out["timing"] is None
    assert out["pattern"] is None
    assert "timing" in out["withheld"]
    assert "pattern" in out["withheld"]
    assert "score" in out["withheld"]
    assert out["situation"] is None


def test_bodied_reports_sequence_and_intervals():
    out = coach_from_sidecar(
        _side(
            events=[
                {"clock_ns": 1_100_000_000, "name": "R2", "kind": "trigger"},
                {"clock_ns": 1_250_000_000, "name": "X", "kind": "press"},
            ]
        )
    )
    assert out["bodied"] is True
    assert out["timing"]["event_count"] == 2
    assert out["timing"]["intervals_ms"] == [150.0]
    assert out["pattern"]["sequence"] == ["R2", "X"]
    assert "timing" not in out["withheld"]


def test_locked_score_is_observed_not_invented():
    out = coach_from_sidecar(
        _side(
            situation={"board_locked": True, "home_score": 21, "away_score": 14},
        )
    )
    assert out["situation"] == {
        "board_locked": True,
        "home_score": 21,
        "away_score": 14,
    }
    assert "score" not in out["withheld"]


def test_unlocked_digits_in_sidecar_still_withheld():
    raw = _side()
    raw["situation"]["home_score"] = 99
    raw["situation"]["board_locked"] = False
    out = coach_from_sidecar(raw)
    assert out["situation"] is None
    assert "score" in out["withheld"]


def test_coach_clip_file_and_stem(tmp_path):
    data = _side()
    p = tmp_path / "hdmi_c.coupling.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    by_path = coach_clip(str(p), clips_dir=tmp_path)
    assert by_path["ok"] is True
    by_stem = coach_clip("hdmi_c", clips_dir=tmp_path)
    assert by_stem["ok"] is True
    missing = coach_clip("nope", clips_dir=tmp_path)
    assert missing["ok"] is False
    assert resolve_coupling_file("../etc/passwd", clips_dir=tmp_path) is None
