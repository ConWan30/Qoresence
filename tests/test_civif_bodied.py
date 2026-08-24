"""Bodied DualSense invariant for live ticks, coaches, and highlights."""

from __future__ import annotations

import json

from qoresence.core.civif_tick import (
    CoachingReport,
    EventRecord,
    build_coupled_tick,
)
from qoresence.core.coupled_event import (
    build_coupling_sidecar,
    set_live_situation_hook,
)
from qoresence.foundry.cer_log import CerLog
from qoresence.foundry.coach import coach_from_sidecar, live_coach
from qoresence.foundry.highlights import get_coupled_clips, rank_highlights
from qoresence.mcp.server import TOOL_DEFS, handle_civif_query_clips


def teardown_function() -> None:
    set_live_situation_hook(None)


def test_tick_unbodied_wipes_input_ticks():
    rec = build_coupled_tick(
        coupling={"video_clock_ns": 9, "frame_seq": 1, "imu_bodied": False},
        events=[],
        session_id="s1",
    )
    d = rec.to_dict()
    assert d["schema_version"] == "civif_tick-1"
    assert d["controller_bodied"] is False
    assert d["input_ticks"] == []
    assert d["input"]["events"] == []


def test_tick_bodied_keeps_mapped_edges():
    rec = build_coupled_tick(
        coupling={"video_clock_ns": 20, "frame_seq": 2, "imu_bodied": True},
        events=[{"name": "R2", "kind": "press", "clock_ns": 19, "value": 1.0}],
    )
    d = rec.to_dict()
    assert d["controller_bodied"] is True
    assert d["input_ticks"][0]["button"] == "R2"
    assert d["input_ticks"][0]["edge_type"] == "press"


def test_unlocked_board_wipes_score_fields():
    set_live_situation_hook(lambda: {"board_locked": False, "home_score": 99, "away_score": 1})
    rec = build_coupled_tick(coupling={"video_clock_ns": 1, "imu_bodied": False})
    d = rec.to_dict()
    assert d["board_locked"] is False
    assert d["situation_snapshot"] is None
    assert d["situation"]["home_score"] is None


def test_cer_mid_session_flag_follows_last_tick():
    log = CerLog(jsonl_path=None)
    log.observe({"video_clock_ns": 10, "frame_seq": 1, "imu_bodied": False})
    assert log.last()["controller_bodied"] is False
    log.observe({"video_clock_ns": 20, "frame_seq": 2, "imu_bodied": True})
    assert log.last()["controller_bodied"] is True
    log.observe({"video_clock_ns": 30, "frame_seq": 3, "imu_bodied": False})
    assert log.last()["controller_bodied"] is False


def test_live_coach_withholds_timing_when_unbodied():
    log = CerLog(jsonl_path=None)
    log.observe({"video_clock_ns": 5, "imu_bodied": False, "coupling": 0.2})
    from qoresence.foundry import cer_log as cer_mod

    prev = cer_mod._log
    cer_mod._log = log
    try:
        out = live_coach()
    finally:
        cer_mod._log = prev
    assert out["ok"] is True
    assert "timing" in out["withheld"]
    assert out.get("timing") is None


def test_coach_from_sidecar_shows_sequence_when_bodied():
    data = build_coupling_sidecar(
        clip_id="b",
        session_id="s",
        start_ns=1_000,
        end_ns=2_000,
        frame_start=0,
        frame_end=1,
        video_path="b.mp4",
        events=[{"clock_ns": 1_100, "name": "X", "kind": "press"}],
        coupling={"imu_bodied": True, "coupling": 0.5},
        coupling_history=[],
    )
    out = coach_from_sidecar(data)
    assert out["bodied"] is True
    assert "timing" not in out["withheld"]
    assert out.get("timing") is not None


def _clip(tmp_path, stem, **kw):
    payload = build_coupling_sidecar(
        clip_id=stem,
        session_id=kw.get("session_id", ""),
        start_ns=1_000_000_000,
        end_ns=2_000_000_000,
        frame_start=1,
        frame_end=2,
        video_path=f"{stem}.mp4",
        events=kw.get("events", []),
        coupling=kw.get("coupling", {}),
        coupling_history=[],
        situation=kw.get("situation"),
    )
    (tmp_path / f"{stem}.mp4").write_bytes(b"x")
    (tmp_path / f"{stem}.coupling.json").write_text(json.dumps(payload), encoding="utf-8")


def test_highlights_key_inputs_only_when_bodied(tmp_path):
    _clip(
        tmp_path,
        "unbodied",
        coupling={"coupling": 0.8},
        events=[],
        situation={"board_locked": True, "home_score": 7, "away_score": 0, "clutch_kind": "score"},
    )
    _clip(
        tmp_path,
        "bodied",
        coupling={"coupling": 0.8, "imu_bodied": True},
        events=[{"clock_ns": 1_100_000_000, "name": "R2", "kind": "press"}],
        situation={"board_locked": True, "home_score": 7, "away_score": 0, "clutch_kind": "score"},
    )
    hits = {h["stem"]: h for h in rank_highlights(tmp_path, limit=8)["hits"]}
    assert hits["unbodied"]["explanation"]["key_inputs"] == []
    assert "R2" in hits["bodied"]["explanation"]["key_inputs"]
    assert hits["bodied"]["explanation"]["outcome_tag"] == "score"
    assert hits["unbodied"]["explanation"]["outcome_tag"] == "score"


def test_query_filters(tmp_path):
    _clip(tmp_path, "low", coupling={"coupling": 0.1})
    _clip(
        tmp_path,
        "hi_lock",
        session_id="sess-a",
        coupling={"coupling": 0.9, "imu_bodied": True},
        events=[{"clock_ns": 1_100_000_000, "name": "L2", "kind": "press"}],
        situation={"board_locked": True, "home_score": 3, "away_score": 0, "clutch_score": 0.8},
    )
    q = get_coupled_clips(
        clips_dir=tmp_path,
        min_coupling_score=0.5,
        board_locked_only=True,
        controller_bodied_only=True,
        session_id="sess-a",
        situation_filters={"clutch_score_min": 0.5},
    )
    assert q["count"] == 1
    assert q["hits"][0]["stem"] == "hi_lock"
    miss = get_coupled_clips(clips_dir=tmp_path, session_id="other")
    assert miss["count"] == 0


def test_mcp_query_tool_registered_not_export():
    names = {t["name"] for t in TOOL_DEFS}
    assert "civif_query_clips" in names
    assert "export_clip" not in names
    assert "civif_coaching_report" not in names
    assert "civif_narrative" not in names
    out = handle_civif_query_clips(limit=1)
    assert out["ok"] is True
    assert CoachingReport(session_id="x").schema_version == "coach-1"
    assert EventRecord(
        session_id="x",
        event_id="e",
        event_type="play",
        t_start_ns=1,
        t_end_ns=2,
        frame_start=0,
        frame_end=1,
    ).schema_version == "event-1"
