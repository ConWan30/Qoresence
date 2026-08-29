"""Foundry index over civif-v0 coupling sidecars. Observation / read-only."""

from __future__ import annotations

import json

from qoresence.core.coupled_event import build_coupling_sidecar, summarize_coupling_for_index
from qoresence.foundry.index import scan_clips, search_clips


def _write_clip(d, stem, *, sidecar):
    mp4 = d / f"{stem}.mp4"
    mp4.write_bytes(b"fake")
    (d / f"{stem}.coupling.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return mp4


def test_unbodied_pad_does_not_match_button_query(tmp_path):
    empty = build_coupling_sidecar(
        clip_id="hdmi_empty",
        session_id="",
        start_ns=1000,
        end_ns=2000,
        frame_start=1,
        frame_end=2,
        video_path="hdmi_empty.mp4",
        events=[],
        coupling={},
        coupling_history=[],
    )
    _write_clip(tmp_path, "hdmi_empty", sidecar=empty)
    hits = search_clips("R2", clips_dir=tmp_path, limit=8)
    assert hits["ok"] is True
    assert hits["count"] == 0
    unb = search_clips("unbodied", clips_dir=tmp_path, limit=8)
    assert unb["count"] == 1
    civ = unb["hits"][0]["civif"]
    assert civ["bodied"] is False
    assert civ["present"] is True


def test_bodied_events_are_searchable(tmp_path):
    side = build_coupling_sidecar(
        clip_id="hdmi_r2",
        session_id="",
        start_ns=1000,
        end_ns=2000,
        frame_start=1,
        frame_end=2,
        video_path="hdmi_r2.mp4",
        events=[{"clock_ns": 1500, "name": "R2", "kind": "trigger"}],
        coupling={"coupling": 0.8},
        coupling_history=[],
    )
    _write_clip(tmp_path, "hdmi_r2", sidecar=side)
    hits = search_clips("R2", clips_dir=tmp_path, limit=8)
    assert hits["count"] == 1
    assert hits["hits"][0]["civif"]["bodied"] is True


def test_scores_only_when_board_locked(tmp_path):
    locked = build_coupling_sidecar(
        clip_id="hdmi_score",
        session_id="",
        start_ns=1000,
        end_ns=2000,
        frame_start=1,
        frame_end=2,
        video_path="hdmi_score.mp4",
        events=[],
        coupling={},
        coupling_history=[],
        situation={
            "board_locked": True,
            "home_score": 21,
            "away_score": 14,
        },
    )
    _write_clip(tmp_path, "hdmi_score", sidecar=locked)
    hits = search_clips("21-14", clips_dir=tmp_path, limit=8)
    assert hits["count"] == 1
    assert hits["hits"][0]["civif"]["board_locked"] is True


def test_unlocked_digits_not_indexed():
    raw = build_coupling_sidecar(
        clip_id="x",
        session_id="",
        start_ns=1,
        end_ns=2,
        frame_start=0,
        frame_end=0,
        video_path="x.mp4",
        events=[],
        coupling={},
        coupling_history=[],
    )
    raw["situation"]["home_score"] = 99
    raw["situation"]["away_score"] = 99
    raw["situation"]["board_locked"] = False
    card = summarize_coupling_for_index(raw)
    assert "99-99" not in card["search_tokens"]
    assert card["home_score"] is None


def test_coupling_min_uses_sidecar(tmp_path, monkeypatch):
    import sys
    from unittest.mock import MagicMock

    class _MockTimeline:
        def recent(self, n):
            return []

    mock_module = MagicMock()
    mock_module.get_session_timeline = lambda: _MockTimeline()
    
    sys.modules['qoresence.agents.session_timeline'] = mock_module
    monkeypatch.setenv("QORESENCE_CLIPS_DIR", str(tmp_path))

    low = build_coupling_sidecar(
        clip_id="hdmi_low",
        session_id="",
        start_ns=1000,
        end_ns=2000,
        frame_start=1,
        frame_end=2,
        video_path="hdmi_low.mp4",
        events=[],
        coupling={"coupling": 0.1},
        coupling_history=[],
    )
    _write_clip(tmp_path, "hdmi_low", sidecar=low)
    none = search_clips("", clips_dir=tmp_path, limit=8, coupling_min=0.5)
    assert none["count"] == 0
    some = search_clips("", clips_dir=tmp_path, limit=8, coupling_min=0.05)
    assert some["count"] == 1


def test_scan_clips_attaches_civif(tmp_path):
    side = build_coupling_sidecar(
        clip_id="hdmi_scan",
        session_id="",
        start_ns=1000,
        end_ns=2000,
        frame_start=1,
        frame_end=2,
        video_path="hdmi_scan.mp4",
        events=[],
        coupling={},
        coupling_history=[],
    )
    _write_clip(tmp_path, "hdmi_scan", sidecar=side)
    rows = scan_clips(tmp_path)
    assert len(rows) == 1
    assert rows[0]["civif"]["schema_version"] == "civif-v0"


def test_scan_clips_max_n_keeps_newest(tmp_path):
    import os

    for i, stem in enumerate(("old", "mid", "new")):
        side = build_coupling_sidecar(
            clip_id=stem,
            session_id="",
            start_ns=1000,
            end_ns=2000,
            frame_start=1,
            frame_end=2,
            video_path=f"{stem}.mp4",
            events=[],
            coupling={},
            coupling_history=[],
        )
        _write_clip(tmp_path, stem, sidecar=side)
        os.utime(tmp_path / f"{stem}.mp4", (1_000 + i, 1_000 + i))
    rows = scan_clips(tmp_path, max_n=2)
    assert [r["stem"] for r in rows] == ["new", "mid"]
