"""SEQGATE × Memory Engineering v0 — stamped write, stale-as-live refuse."""

from __future__ import annotations

import json
from pathlib import Path

from qoresence.sync.digit_integrity import CONFIRM_DIGIT_MAX_AGE_NS

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "seqgate_memory_receipts.jsonl"

LICENSED_STAMP = {
    "clock_ns": 2_000,
    "frame_seq": 42,
    "crop_hash": "crop-a",
    "path": "confirm",
    "seqgate": "licensed",
    "reason": "licensed",
    "ticket_id": "c-1",
}


def _rows() -> list[dict]:
    return [
        json.loads(line)
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_unstamped_write_refused(tmp_path):
    from qoresence.agents.session_memory import SessionMemory
    from qoresence.agents.situation_model import SituationModel
    from qoresence.sync.seqgate import accept_memory_write

    bare = accept_memory_write({"home_score": 14, "away_score": 10})
    assert bare["accepted"] is False
    assert bare["refuse"] == "unstamped"

    missing_clock = accept_memory_write({**LICENSED_STAMP, "clock_ns": None})
    assert missing_clock["accepted"] is False
    assert missing_clock["refuse"] == "unstamped"

    no_crop_key = {k: v for k, v in LICENSED_STAMP.items() if k != "crop_hash"}
    assert accept_memory_write(no_crop_key)["accepted"] is False

    path = tmp_path / "memory.jsonl"
    memory = SessionMemory(output_path=path)
    result = memory.record(moment=None, situation=SituationModel(), results=[{"ok": True}])
    assert result["accepted"] is False
    assert result["refuse"] == "unstamped"
    assert path.exists() is False or path.read_text(encoding="utf-8").strip() == ""


def test_licensed_write_requires_ticket_and_keeps_stamp(tmp_path):
    from qoresence.agents.session_memory import SessionMemory
    from qoresence.agents.situation_model import SituationModel
    from qoresence.sync.seqgate import accept_memory_write

    no_ticket = {**LICENSED_STAMP, "ticket_id": ""}
    refused = accept_memory_write(no_ticket)
    assert refused["accepted"] is False
    assert refused["refuse"] == "missing_ticket"

    ok = accept_memory_write({**LICENSED_STAMP, "home_score": 14, "away_score": 10})
    assert ok["accepted"] is True
    stamp = ok["stamp"]
    assert stamp["clock_ns"] == 2_000
    assert stamp["frame_seq"] == 42
    assert stamp["crop_hash"] == "crop-a"
    assert stamp["path"] == "confirm"
    assert stamp["seqgate"] == "licensed"
    assert stamp["reason"] == "licensed"
    assert stamp["ticket_id"] == "c-1"

    path = tmp_path / "memory.jsonl"
    memory = SessionMemory(output_path=path)
    written = memory.record(
        moment=None,
        situation=SituationModel(),
        results=[{"ok": True}],
        stamp={**LICENSED_STAMP, "home_score": 14, "away_score": 10},
    )
    assert written["accepted"] is True
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["clock_ns"] == 2_000
    assert entry["frame_seq"] == 42
    assert entry["crop_hash"] == "crop-a"
    assert entry["path"] == "confirm"
    assert entry["seqgate"] == "licensed"
    assert entry["reason"] == "licensed"
    assert entry["ticket_id"] == "c-1"

    noop = memory.record(
        moment=None,
        situation=SituationModel(),
        results=[{"ok": True}],
        stamp={**LICENSED_STAMP, "clock_ns": 3_000},
    )
    assert noop["accepted"] is False
    assert noop["refuse"] == "same_seq_noop"
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_explicit_empty_crop_hash_is_stamped():
    from qoresence.sync.seqgate import accept_memory_write

    hold = {
        "clock_ns": 1,
        "frame_seq": 0,
        "crop_hash": "",
        "path": "confirm",
        "seqgate": "hold",
        "reason": "ticket_stale",
    }
    got = accept_memory_write(hold)
    assert got["accepted"] is True
    assert got["stamp"]["crop_hash"] == ""
    assert got["stamp"]["seqgate"] == "hold"


def test_stale_memory_cannot_license_digits():
    from qoresence.sync.seqgate import NULL_DIGIT, license_memory_speech

    memory = {
        **LICENSED_STAMP,
        "home_score": 14,
        "away_score": 10,
        "score_vlm_locked": True,
    }
    gate = license_memory_speech(
        memory,
        live_clock_ns=3_000,
        live_frame_seq=99,
        live_crop_hash="crop-a",
        score_vlm_locked=True,
    )
    assert gate["licensed"] is False
    assert gate["speech"] == NULL_DIGIT
    assert "14" not in gate["speech"]
    assert gate["reason"] in {"seq_skew", "ticket_stale"}

    aged = license_memory_speech(
        memory,
        live_clock_ns=2_000 + CONFIRM_DIGIT_MAX_AGE_NS + 1,
        live_frame_seq=42,
        live_crop_hash="crop-a",
        score_vlm_locked=True,
    )
    assert aged["licensed"] is False
    assert aged["speech"] == NULL_DIGIT
    assert aged["reason"] == "ticket_stale"


def test_licensed_fresh_passes_stamp_fields_fast_invents_no_digits():
    from qoresence.sync.seqgate import NULL_DIGIT, accept_memory_write, license_memory_speech

    fresh = license_memory_speech(
        {**LICENSED_STAMP, "home_score": 14, "away_score": 10, "score_vlm_locked": True},
        live_clock_ns=2_500,
        live_frame_seq=42,
        live_crop_hash="crop-a",
        score_vlm_locked=True,
    )
    assert fresh["licensed"] is True
    assert fresh["speech"] == "14-10"
    assert fresh["bind"]["clock_ns"] == 2_500
    assert fresh["bind"]["frame_seq"] == 42
    assert fresh["bind"]["path"] == "confirm"

    fast_stamp = {
        "clock_ns": 2_000,
        "frame_seq": 42,
        "crop_hash": "crop-a",
        "path": "fast",
        "seqgate": "hold",
        "reason": "path_fast",
        "home_score": 14,
        "away_score": 10,
    }
    wrote = accept_memory_write(fast_stamp)
    assert wrote["accepted"] is True
    assert wrote["stamp"]["path"] == "fast"
    assert wrote["stamp"]["seqgate"] == "hold"

    fast_speech = license_memory_speech(
        fast_stamp,
        live_clock_ns=2_500,
        live_frame_seq=42,
        live_crop_hash="crop-a",
        score_vlm_locked=True,
    )
    assert fast_speech["licensed"] is False
    assert fast_speech["speech"] == NULL_DIGIT
    assert fast_speech["reason"] == "path_fast"
    assert "14" not in fast_speech["speech"]

    licensed_on_fast = accept_memory_write({**LICENSED_STAMP, "path": "fast"})
    assert licensed_on_fast["accepted"] is False
    assert licensed_on_fast["refuse"] == "path_fast"


def test_agent_glass_and_observation_refuse_stale_memory_as_live():
    from qoresence.agents.agent_glass import AgentGlass
    from qoresence.mcp.observation import build_observation
    from qoresence.sync.seqgate import NULL_DIGIT

    memory = {
        **LICENSED_STAMP,
        "home_score": 14,
        "away_score": 10,
        "score_vlm_locked": True,
    }
    # Last-good lie: situation copies memory digits and claims same_seq.
    live_sit = {
        "home_score": 14,
        "away_score": 10,
        "confirm_ticket_id": "c-1",
        "score_vlm_locked": True,
        "path": "confirm",
        "ticket_crop_hash": "crop-a",
        "crop_hash": "crop-a",
        "same_seq": True,
        "confirm_clock_ns": 2_000,
        "clock_ns": 3_000,
        "frame_seq": 99,
    }
    g = AgentGlass(situation_provider=lambda: live_sit)
    snap = g.snapshot(memory_entry=memory)
    assert snap["situation"]["home_score"] is None
    assert snap["situation"]["away_score"] is None
    assert snap["memory"]["licensed"] is False
    assert snap["memory"]["speech"] == NULL_DIGIT
    assert snap["seqgate"]["speech"] == NULL_DIGIT
    assert "14" not in str(snap["seqgate"]["speech"])

    obs = build_observation(
        situation=live_sit,
        video={"has_frame": True, "seq": 99, "crop_hash": "crop-a"},
        clock_ns=3_000,
        seq=99,
        memory=memory,
    )
    assert obs["score"]["claim"] is False
    assert obs["score"]["home"] is None
    assert "14-10" not in " ".join(obs["may_say"])
    assert obs["memory"]["licensed"] is False
    assert obs["memory"]["speech"] == NULL_DIGIT
    assert obs["seqgate"]["speech"] == NULL_DIGIT


def test_fixture_licensed_write_vs_stale_refuse(tmp_path):
    from qoresence.agents.session_memory import SessionMemory
    from qoresence.agents.situation_model import SituationModel
    from qoresence.sync.seqgate import NULL_DIGIT, accept_memory_write, license_memory_speech

    rows = {row["case"]: row for row in _rows()}
    assert "licensed_write" in rows
    assert "unstamped_write" in rows
    assert "stale_speech" in rows

    path = tmp_path / "receipts.jsonl"
    memory = SessionMemory(output_path=path)

    licensed = rows["licensed_write"]
    got = accept_memory_write(licensed)
    assert got["accepted"] is True
    written = memory.record(moment=None, situation=SituationModel(), results=[], stamp=licensed)
    assert written["accepted"] is True

    unstamped = accept_memory_write(rows["unstamped_write"])
    assert unstamped["accepted"] is False
    assert unstamped["refuse"] == rows["unstamped_write"]["expect_refuse"]

    stale = rows["stale_speech"]
    gate = license_memory_speech(
        stale,
        live_clock_ns=int(stale["live_clock_ns"]),
        live_frame_seq=int(stale["live_frame_seq"]),
        live_crop_hash=str(stale["live_crop_hash"]),
        score_vlm_locked=bool(stale.get("score_vlm_locked")),
    )
    assert gate["licensed"] is False
    assert gate["speech"] == stale["expect_speech"] == NULL_DIGIT

    fresh = rows["licensed_fresh_speech"]
    fresh_gate = license_memory_speech(
        fresh,
        live_clock_ns=int(fresh["live_clock_ns"]),
        live_frame_seq=int(fresh["live_frame_seq"]),
        live_crop_hash=str(fresh["live_crop_hash"]),
        score_vlm_locked=bool(fresh.get("score_vlm_locked")),
    )
    assert fresh_gate["licensed"] is True
    assert fresh_gate["speech"] == fresh["expect_speech"]

    fast = rows["fast_stamp_no_digits"]
    assert accept_memory_write(fast)["accepted"] is True
    fast_gate = license_memory_speech(
        fast,
        live_clock_ns=int(fast["live_clock_ns"]),
        live_frame_seq=int(fast["live_frame_seq"]),
        live_crop_hash=str(fast["live_crop_hash"]),
        score_vlm_locked=bool(fast.get("score_vlm_locked")),
    )
    assert fast_gate["licensed"] is False
    assert fast_gate["speech"] == NULL_DIGIT
