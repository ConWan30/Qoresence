"""Live licensed narrative flush — Story/Recap must not stay not_persisted during play."""

from __future__ import annotations

from qoresence.foundry import narrative_engine as ne
from qoresence.foundry import session_view as sv
from qoresence.foundry.narrative_engine import (
    build_licensed_tick,
    last_narrative,
    maybe_flush_live_narrative,
    note_licensed_tick,
    reset_live_narrative_state,
)


def _licensed_sit(home=7, away=0, yard=50, ticket="ticket-live"):
    return {
        "score_vlm_locked": True,
        "confirm_ticket_id": ticket,
        "home_score": home,
        "away_score": away,
        "yard_line": yard,
    }


def _setup():
    ne._last.clear()
    reset_live_narrative_state()


def test_licensed_flush_populates_last_narrative():
    _setup()
    sid = "qoresence_live_flush"
    t1 = build_licensed_tick(_licensed_sit(home=0, away=0), clock_ns=1_000, frame_seq=10)
    t2 = build_licensed_tick(_licensed_sit(home=7, away=0), clock_ns=2_000, frame_seq=20)
    assert t1 and t2
    note_licensed_tick(sid, t1)
    note_licensed_tick(sid, t2)
    pack = maybe_flush_live_narrative(sid)
    assert pack is not None
    assert pack["session_id"] == sid
    assert pack["board_locked"] is True
    assert pack["events"]
    types = {e["event_type"] for e in pack["events"]}
    assert "situation_shift" in types
    stored = last_narrative(sid)
    assert stored is not None
    assert stored["events"]


def test_live_view_no_longer_not_persisted_after_flush():
    _setup()
    sid = "qoresence_view_live"
    note_licensed_tick(
        sid,
        build_licensed_tick(_licensed_sit(home=10, away=10), clock_ns=4_000, frame_seq=41),
    )
    note_licensed_tick(
        sid,
        build_licensed_tick(_licensed_sit(home=14, away=10), clock_ns=5_000, frame_seq=42),
    )
    maybe_flush_live_narrative(sid, force=True)
    env = sv.build_session_response(session_id=sid)
    assert env["status"] == "live"
    assert env["view"]["empty_reason"] is None
    assert env["view"]["events"]
    shift = next(e for e in env["view"]["events"] if e["event_type"] == "situation_shift")
    assert shift["score"] == {"home": 14, "away": 10}


def test_live_flush_uses_buffered_ticks_not_cer_log(monkeypatch):
    _setup()

    def boom():
        raise AssertionError("generate_narrative must not read cer_log when ticks are buffered")

    monkeypatch.setattr("qoresence.foundry.cer_log.get_cer_log", boom)

    sid = "qoresence_no_cer"
    tick = build_licensed_tick(_licensed_sit(), clock_ns=1, frame_seq=1)
    assert tick
    note_licensed_tick(sid, tick)
    maybe_flush_live_narrative(sid, force=True)


def test_unlicensed_situation_does_not_build_tick():
    tick = build_licensed_tick(
        {"score_vlm_locked": True, "confirm_ticket_id": "", "home_score": 7, "away_score": 0},
        clock_ns=1,
        frame_seq=1,
    )
    assert tick is None


def test_flush_throttles_same_score_key():
    _setup()
    sid = "qoresence_throttle"
    tick = build_licensed_tick(_licensed_sit(home=0, away=0), clock_ns=1, frame_seq=1)
    assert tick
    note_licensed_tick(sid, tick)
    first = maybe_flush_live_narrative(sid, force=True)
    assert first is not None
    ne._last.clear()
    second = maybe_flush_live_narrative(sid)
    assert second is None
    assert last_narrative(sid) is None
    note_licensed_tick(
        sid,
        build_licensed_tick(_licensed_sit(home=7, away=0), clock_ns=2, frame_seq=2),
    )
    third = maybe_flush_live_narrative(sid)
    assert third is not None
    assert third["events"]
