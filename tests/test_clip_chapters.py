"""Clip chapters unit tests (offline)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from qoresence.agents.session_timeline import SessionTimeline, reset_session_timeline
from qoresence.vision.clip_chapters import (
    build_chapters_for_window,
    chapters_after_export,
    write_clip_sidecar,
)


def test_chapters_ordered_by_t_s():
    end = time.monotonic_ns()
    events = [
        type("E", (), {"to_dict": lambda self: {
            "clock_ns": end - int(2e9),
            "kind": "fast_chat",
            "message": "late",
            "path": "fast",
        }})(),
        type("E", (), {"to_dict": lambda self: {
            "clock_ns": end - int(4e9),
            "kind": "arm",
            "message": "early",
            "path": "fast",
        }})(),
    ]
    # Fix lambdas - use simple dicts instead
    events = [
        {"clock_ns": end - int(2e9), "kind": "fast_chat", "message": "late", "path": "fast"},
        {"clock_ns": end - int(4e9), "kind": "arm", "message": "early", "path": "fast"},
    ]
    ch = build_chapters_for_window(5.0, events, window_end_ns=end)
    assert len(ch) >= 2
    assert ch[0]["t_s"] <= ch[1]["t_s"]
    assert ch[0]["label"] == "early"


def test_sidecar_written(tmp_path: Path):
    mp4 = tmp_path / "hdmi_clip_test.mp4"
    mp4.write_bytes(b"fake")
    out = write_clip_sidecar(
        mp4,
        [{"t_s": 0.5, "label": "mark", "kind": "fast_chat"}],
        buttons={"r1": 1},
        why={"line": "path=fast · test"},
        duration_s=5.0,
        graph_summary={
            "phase": "resolved",
            "match_rate": 1.0,
            "drive_id": "d1",
            "climax": {"score": 0.8, "best_label": "x", "has_fast_confirm": True},
        },
    )
    assert out is not None and out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["chapters"][0]["t_s"] == 0.5
    assert data["buttons"]["r1"] == 1
    assert "why" in data
    assert data["graph_summary"]["phase"] == "resolved"


def test_snapshot_why_last_after_append():
    reset_session_timeline()
    from qoresence.agents.session_timeline import get_session_timeline

    tl = get_session_timeline()
    tl.append(kind="fast_chat", path="fast", message="heat", coupling=0.7, clock_ns=1)
    snap = tl.snapshot()
    assert snap["why_last"] is not None
    assert "heat" in snap["why_last"]["line"]


def test_chapters_after_export(tmp_path: Path, monkeypatch):
    reset_session_timeline()
    from qoresence.agents.session_timeline import get_session_timeline

    tl = get_session_timeline()
    now = time.monotonic_ns()
    tl.append(kind="fast_clip", path="fast", message="clip", clock_ns=now - int(1e9))
    mp4 = tmp_path / "hdmi_clip_x.mp4"
    mp4.write_bytes(b"x")
    out = chapters_after_export(mp4, 5.0)
    assert out is not None
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "chapters" in data
