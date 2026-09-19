"""Judgment ledger v0 — Society write sink / OCCF soft-act compose.

Locks in: seven-pack catalog, fail-closed bind states, licenses_digits False,
and no score/ticket/pixel leakage on the ledger row.
"""

from __future__ import annotations

import json
from pathlib import Path

from qoresence.agents.society.judgment_ledger import (
    BIND_STATES,
    PACKS,
    SCHEMA,
    compose_soft_act,
    ledger_stats,
    note_judgment,
    note_pack_verdict,
    reset_ledger_for_tests,
    row_has_leakage,
)


def setup_function(_fn=None):
    pass


def _fresh(tmp_path: Path):
    reset_ledger_for_tests(out_dir=tmp_path)


def test_seven_packs_frozen():
    assert PACKS == (
        "conductor",
        "noul",
        "press",
        "recap",
        "coroner",
        "ticket_stale",
        "score_plausibility",
    )
    assert "connector" not in PACKS
    assert "ticket_glass" not in PACKS
    assert "sync_glass" not in PACKS


def test_bind_bound_with_clock(tmp_path):
    _fresh(tmp_path)
    row = compose_soft_act(
        pack="press",
        tool="press_label",
        action="act",
        speech="none",
        clock_ns=1_000_000_042,
        frame_seq=7,
        source="local_heuristic",
        verdict={"outcome": "labeled", "source": "local_heuristic"},
    )
    assert row["schema"] == SCHEMA
    assert row["licenses_digits"] is False
    assert row["correlation"]["state"] == "bound"
    assert row["observatory"]["clock_ns"] == 1_000_000_042
    assert row["observatory"]["frame_seq"] == 7
    assert row["compose"]["action"] == "act"
    assert row_has_leakage(row) == []


def test_bind_unbound_when_clock_missing(tmp_path):
    _fresh(tmp_path)
    row = compose_soft_act(
        pack="conductor",
        clock_ns=0,
        frame_seq=0,
        verdict={"fast_act": "chat_red_zone", "observe": "silent", "source": "local_heuristic"},
        source="local_heuristic",
    )
    assert row["correlation"]["state"] == "unbound"
    assert row["observatory"]["clock_ns"] == 0
    assert row["observatory"]["frame_seq"] == 0
    # Must not invent a monotonic stamp.
    assert row["observatory"]["clock_ns"] == 0
    assert row["licenses_digits"] is False


def test_bind_stale(tmp_path):
    _fresh(tmp_path)
    row = compose_soft_act(
        pack="ticket_stale",
        clock_ns=99,
        frame_seq=3,
        stale=True,
        verdict={"action": "flag_stale", "stale_class": "crop_moved_on", "source": "typesafe"},
        source="typesafe",
    )
    assert row["correlation"]["state"] == "stale"
    assert row["compose"]["speech"] in {"boxes", "none"}
    assert row["licenses_digits"] is False


def test_bind_denied_preflight(tmp_path):
    _fresh(tmp_path)
    row = compose_soft_act(
        pack="conductor",
        clock_ns=50,
        frame_seq=1,
        deny_reason="truth/humanity/ban claim refused at preflight",
        source="preflight",
    )
    assert row["correlation"]["state"] == "denied"
    assert row["compose"]["action"] == "deny"
    assert row["compose"]["deny_reason"]
    assert row["licenses_digits"] is False


def test_unknown_pack_denied(tmp_path):
    _fresh(tmp_path)
    row = compose_soft_act(pack="connector", clock_ns=1, frame_seq=1)
    assert row["correlation"]["state"] == "denied"
    assert "connector" not in PACKS


def test_no_score_ticket_pixel_leakage(tmp_path):
    _fresh(tmp_path)
    dirty = {
        "fast_act": "chat_red_zone",
        "observe": "board_licensed",
        "home_score": 21,
        "away_score": 17,
        "confirm_ticket_id": "abcdabcdabcdabcd",
        "crop_jpeg": "/9j/fake",
        "chat": "Board 21-17 late",
        "source": "typesafe",
    }
    row = note_judgment(
        "conductor",
        verdict=dirty,
        clock_ns=123,
        frame_seq=9,
        agent={"brand": "muse", "turn_id": "t1", "asked_at_unix_ms": 1},
    )
    assert row["licenses_digits"] is False
    assert row_has_leakage(row) == []
    blob = json.dumps(row)
    assert "21-17" not in blob
    assert "confirm_ticket" not in blob.lower()
    assert "home_score" not in blob
    assert "crop_jpeg" not in blob
    assert "/9j/" not in blob


def test_note_writes_jsonl(tmp_path):
    _fresh(tmp_path)
    row = note_judgment(
        "noul",
        verdict={"hud_kind": "live_hud", "source": "local_heuristic"},
        clock_ns=5,
        frame_seq=2,
    )
    assert row["correlation"]["state"] == "bound"
    path = tmp_path / "jev_ledger.jsonl"
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    loaded = json.loads(lines[-1])
    assert loaded["schema"] == SCHEMA
    assert loaded["pack"] == "noul"
    assert loaded["licenses_digits"] is False
    assert loaded["correlation"]["state"] in BIND_STATES
    stats = ledger_stats()
    assert stats["rows"] >= 1
    assert stats["licenses_digits"] is False


def test_note_pack_verdict_none_safe(tmp_path):
    _fresh(tmp_path)
    assert note_pack_verdict("press", None) is None
    assert note_pack_verdict("press", "bad") is None  # type: ignore[arg-type]


def test_soft_act_speech_heat_and_boxes(tmp_path):
    _fresh(tmp_path)
    heat = compose_soft_act(
        pack="conductor",
        clock_ns=10,
        frame_seq=1,
        verdict={"fast_act": "chat_clutch_window", "observe": "silent"},
    )
    assert heat["intent"]["tool"] == "heat_chat"
    assert heat["compose"]["speech"] == "heat"
    assert heat["compose"]["action"] == "act"

    boxes = compose_soft_act(
        pack="recap",
        clock_ns=10,
        frame_seq=1,
        verdict={"hold": True, "digit_leak": True, "reason": "digit_leak"},
        deny_reason="digit_leak",
    )
    assert boxes["correlation"]["state"] == "denied"
    assert boxes["compose"]["action"] == "deny"


def test_all_bind_states_reachable(tmp_path):
    _fresh(tmp_path)
    seen = set()
    seen.add(
        compose_soft_act(pack="press", clock_ns=1, frame_seq=1, verdict={"outcome": "labeled"})[
            "correlation"
        ]["state"]
    )
    seen.add(
        compose_soft_act(pack="press", clock_ns=0, frame_seq=0, verdict={"outcome": "unlabeled"})[
            "correlation"
        ]["state"]
    )
    seen.add(
        compose_soft_act(
            pack="ticket_stale", clock_ns=1, frame_seq=1, stale=True, verdict={"action": "flag_stale"}
        )["correlation"]["state"]
    )
    seen.add(
        compose_soft_act(pack="recap", deny_reason="mid_drive", clock_ns=1, frame_seq=1)[
            "correlation"
        ]["state"]
    )
    assert seen == {"bound", "unbound", "stale", "denied"}
