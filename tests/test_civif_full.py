"""Full CIVIF: live CER, fail-closed situation, highlight query."""

from __future__ import annotations

import json

from qoresence.core.coupled_event import (
    build_coupling_sidecar,
    current_situation,
    set_live_situation_hook,
    situation_from_live_snapshot,
)
from qoresence.foundry.cer_log import CerLog
from qoresence.foundry.coach import live_coach
from qoresence.foundry.highlights import rank_highlights


def teardown_function() -> None:
    set_live_situation_hook(None)


def test_unlocked_snapshot_strips_digits():
    sit = situation_from_live_snapshot(
        {"score_vlm_locked": False, "home_score": 99, "away_score": 1}
    )
    assert sit["board_locked"] is False
    assert sit["home_score"] is None
    assert sit["away_score"] is None


def test_locked_snapshot_keeps_digits():
    sit = situation_from_live_snapshot(
        {"score_vlm_locked": True, "home_score": 21, "away_score": 14, "game_title": "Madden"}
    )
    assert sit["board_locked"] is True
    assert sit["home_score"] == 21
    assert sit["game_title"] == "Madden"


def test_cer_ring_unbodied_and_no_bus_fields():
    log = CerLog(jsonl_path=None)
    log.observe(
        {
            "video_clock_ns": 5,
            "frame_seq": 3,
            "coupling": 0.4,
            "imu_bodied": False,
        }
    )
    rec = log.last()
    assert rec is not None
    assert rec["kind"] == "live_tick"
    assert rec["input"]["bodied"] is False
    assert rec["schema_version"] == "civif_tick-1"
    assert rec["controller_bodied"] is False
    assert rec["input_ticks"] == []
    assert rec["sidecar_schema"] == "civif-v0"


def test_live_coach_withholds_until_record():
    # Singleton ring may be empty or leftover; coach must not invent pad timing.
    set_live_situation_hook(lambda: {"score_vlm_locked": False, "home_score": 3})
    out = live_coach()
    assert out["ok"] is True
    if out.get("live"):
        assert "timing" in out.get("withheld", []) or out.get("bodied") is True
        assert out.get("situation") is None or out["situation"].get("home_score") is None
    else:
        assert "timing" in out["withheld"]


def test_hook_feeds_current_situation():
    set_live_situation_hook(lambda: {"board_locked": True, "home_score": 7, "away_score": 0})
    sit = current_situation()
    assert sit["board_locked"] is True
    assert sit["home_score"] == 7


def test_sidecar_uses_hook_situation():
    set_live_situation_hook(
        lambda: {"score_vlm_locked": True, "home_score": 28, "away_score": 24}
    )
    data = build_coupling_sidecar(
        clip_id="x",
        session_id="",
        start_ns=1,
        end_ns=2,
        frame_start=0,
        frame_end=1,
        video_path="x.mp4",
        events=[],
        coupling={},
        coupling_history=[],
        situation=current_situation(),
    )
    assert data["situation"]["board_locked"] is True
    assert data["situation"]["home_score"] == 28


def test_highlights_rank_bodied_and_locked(tmp_path):
    def _write(stem, **kw):
        payload = build_coupling_sidecar(
            clip_id=stem,
            session_id="",
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

    _write("hdmi_low", coupling={"coupling": 0.1})
    _write(
        "hdmi_hi",
        coupling={"coupling": 0.9, "imu_bodied": True},
        events=[{"clock_ns": 1_100_000_000, "name": "R2", "kind": "press", "hid_domain": "play"}],
        situation={"board_locked": True, "home_score": 14, "away_score": 7},
    )
    out = rank_highlights(tmp_path, limit=8)
    assert out["ok"] is True
    assert out["hits"][0]["stem"] == "hdmi_hi"
    assert "board_locked" in out["hits"][0]["why"]
    assert out["hits"][0]["explanation"]["controller_bodied"] is True
    assert "R2" in out["hits"][0]["explanation"]["key_inputs"]
    assert out["hits"][0]["civif"]["home_score"] == 14
