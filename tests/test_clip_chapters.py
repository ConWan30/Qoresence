"""Clip chapters unit tests (offline)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from qoresence.agents.session_timeline import reset_session_timeline
from qoresence.vision.clip_chapters import (
    SEGMENT_LABELS,
    build_chapters_for_window,
    build_segments_for_window,
    chapters_after_export,
    write_clip_sidecar,
)

S = 1_000_000_000


def test_chapters_ordered_by_t_s():
    end = time.monotonic_ns()
    events = [
        type(
            "E",
            (),
            {
                "to_dict": lambda self: {
                    "clock_ns": end - int(2e9),
                    "kind": "fast_chat",
                    "message": "late",
                    "path": "fast",
                }
            },
        )(),
        type(
            "E",
            (),
            {
                "to_dict": lambda self: {
                    "clock_ns": end - int(4e9),
                    "kind": "arm",
                    "message": "early",
                    "path": "fast",
                }
            },
        )(),
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


def test_segments_clip_to_window_and_include_prior_run():
    runs = [(0, "menu", "idle"), (10 * S, "live_hud", "join"), (40 * S, "loading", "idle")]
    segs = build_segments_for_window(runs, start_ns=5 * S, end_ns=30 * S)
    assert [(s["hud_kind"], s["t0_s"], s["t1_s"]) for s in segs] == [
        ("menu", 0.0, 5.0),
        ("live_hud", 5.0, 25.0),
    ]
    assert segs[1]["label"] == "Live" and segs[1]["presence"] == "join"


def test_segments_hysteresis_folds_flicker():
    runs = [
        (0, "live_hud", "join"),
        (10 * S, "menu", "idle"),
        (10 * S + S // 2, "live_hud", "join"),
    ]
    segs = build_segments_for_window(runs, start_ns=0, end_ns=20 * S)
    assert len(segs) == 1
    assert segs[0]["hud_kind"] == "live_hud"
    assert (segs[0]["t0_s"], segs[0]["t1_s"]) == (0.0, 20.0)


def test_segments_short_leading_run_folds_forward():
    runs = [(0, "loading", "idle"), (S // 2, "live_hud", "join")]
    segs = build_segments_for_window(runs, start_ns=0, end_ns=10 * S)
    assert [(s["hud_kind"], s["t0_s"]) for s in segs] == [("live_hud", 0.0)]


def test_segments_closed_vocabulary():
    runs = [(0, "clutch_moment", "hype"), (5 * S, "menu", "idle")]
    segs = build_segments_for_window(runs, start_ns=0, end_ns=10 * S)
    assert segs[0]["hud_kind"] == "unknown" and segs[0]["presence"] == "unknown"
    assert segs[0]["label"] == "Unknown"
    banned = ("clutch", "highlight", "best", "hype")
    for label in SEGMENT_LABELS.values():
        assert not any(b in label.lower() for b in banned)


def test_segments_empty_window():
    assert build_segments_for_window([(0, "menu", "idle")], start_ns=5, end_ns=5) == []
    assert build_segments_for_window([], start_ns=0, end_ns=10 * S) == []


def test_sidecar_has_no_segments_when_noul_off(tmp_path: Path, monkeypatch):
    from qoresence.observability import noul_observatory

    reset_session_timeline()
    monkeypatch.setattr(noul_observatory, "get_noul_observatory", lambda: None)
    mp4 = tmp_path / "hdmi_clip_off.mp4"
    mp4.write_bytes(b"x")
    out = chapters_after_export(mp4, 5.0)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "segments" not in data
    assert "segments_source" not in data


def test_sidecar_segments_from_noul(tmp_path: Path, monkeypatch):
    from qoresence.observability import noul_observatory

    class FakeObs:
        enabled = True

        def __init__(self):
            self.windows = []

        def runs_in_window(self, start_ns, end_ns):
            self.windows.append((start_ns, end_ns))
            return [(start_ns - S, "menu", "idle"), (start_ns + 4 * S, "live_hud", "dense")]

    fake = FakeObs()
    reset_session_timeline()
    monkeypatch.setattr(noul_observatory, "get_noul_observatory", lambda: fake)
    mp4 = tmp_path / "stem_x.mp4"
    mp4.write_bytes(b"x")
    start = time.monotonic_ns()
    out = chapters_after_export(
        mp4, 10.0, window_start_ns=start, window_end_ns=start + 10 * S
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert fake.windows == [(start, start + 10 * S)]
    assert [s["hud_kind"] for s in data["segments"]] == ["menu", "live_hud"]
    assert data["segments"][1]["t0_s"] == 4.0
    assert data["segments_source"] == "noul"
    assert data["licenses_digits"] is False
