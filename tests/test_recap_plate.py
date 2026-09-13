"""D-PLATE: mark postgame 0–10 as plate/not-final. Do not drop. Do not freeze 21–3."""

from __future__ import annotations

from qoresence.foundry.narrative_engine import generate_narrative
from qoresence.foundry.session_view import normalize_pack, recap_from_envelope
from qoresence.sync.seqgate import NULL_DIGIT, license_digits


def _tick(clock, *, home, away, locked=True):
    return {
        "clock_ns": clock,
        "frame_seq": clock,
        "controller_bodied": False,
        "board_locked": locked,
        "clip_id": "",
        "situation": {
            "board_locked": locked,
            "home_score": home,
            "away_score": away,
        },
    }


def _env(view: dict) -> dict:
    return {
        "ok": True,
        "status": "live",
        "session": "qoresence_06b8c404882b",
        "view": view,
        "freshness": {
            "generated_at": "2026-09-13T15:08:23Z",
            "last_event_at": "2026-09-13T15:08:23Z",
            "age_ms": 0,
            "stale": False,
        },
    }


def test_recap_keeps_locked_21_3_and_marks_0_10_plate():
    ticks = [
        _tick(1_000_000, home=14, away=3, locked=True),
        _tick(2_000_000, home=21, away=3, locked=True),
        _tick(3_000_000, home=0, away=10, locked=True),
    ]
    nar = generate_narrative("qoresence_06b8c404882b", ticks=ticks, persist=False)
    types = [e["event_type"] for e in nar["events"]]
    assert types.count("situation_shift") == 2
    view = normalize_pack({**nar, "persisted": True})
    recap = recap_from_envelope(_env(view))
    assert recap["event_count"] == 2
    first, last = recap["events"][0], recap["events"][-1]
    assert first["score"] == {"home": 21, "away": 3}
    assert first["qualification"] == "confirmed"
    assert first["state"] == "locked"
    assert last["score"] == {"home": 0, "away": 10}
    assert last["qualification"] == "plate"
    assert last["state"] == "unlocked"
    assert last.get("not_final") is True
    assert last["qualification"] != "confirmed"
    assert recap["confirmed_event_count"] == 1
    assert view["current_moment"]["qualification"] == "plate"
    assert view["confirmed"]["score"] != {"home": 0, "away": 10}
    assert view["confirmed"]["available"] is False


def test_plate_does_not_last_good_freeze_21_3_as_current_lock():
    ticks = [
        _tick(1_000_000, home=21, away=3),
        _tick(2_000_000, home=0, away=10),
    ]
    nar = generate_narrative("plate", ticks=ticks, persist=False)
    view = normalize_pack({**nar, "persisted": True})
    recap = recap_from_envelope(_env(view))
    last = recap["events"][-1]
    assert last["score"] == {"home": 0, "away": 10}
    assert last["qualification"] == "plate"
    assert view["confirmed"]["score"] != {"home": 21, "away": 3}


def test_live_speech_null_when_lock_or_fresh_fail():
    stale = license_digits(
        confirm_ticket_id="c-1",
        score_vlm_locked=True,
        path="confirm",
        ticket_crop_hash="crop-a",
        live_crop_hash="crop-a",
        same_seq=True,
        ticket_clock_ns=1,
        live_clock_ns=9_000_000_002,
        frame_seq=1,
        home_score=21,
        away_score=3,
    )
    assert stale["licensed"] is False
    assert stale["speech"] == NULL_DIGIT
    unlocked = license_digits(
        confirm_ticket_id="",
        score_vlm_locked=False,
        path="confirm",
        ticket_crop_hash="",
        live_crop_hash="",
        same_seq=True,
        ticket_clock_ns=0,
        live_clock_ns=1,
        frame_seq=2,
        home_score=0,
        away_score=10,
    )
    assert unlocked["licensed"] is False
    assert unlocked["speech"] == NULL_DIGIT
    assert "21" not in unlocked["speech"]
    assert "10" not in unlocked["speech"] or unlocked["speech"] == NULL_DIGIT
