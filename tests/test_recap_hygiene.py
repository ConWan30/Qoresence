"""Recap hygiene door — hold leaks, never seal."""

from qoresence.compose.clock_notary.door import export_door
from qoresence.observability.recap_hygiene import (
    compose_hygiene,
    inspect_envelope,
    unlocked_digit_leak,
)


def test_unlocked_digits_are_a_leak():
    env = {
        "ticks": [{"score_digits": "14-7", "score_vlm_locked": False, "clock_ns": 1, "frame_seq": 1}],
        "hid_on_console": True,
    }
    assert unlocked_digit_leak(env) is True
    out = compose_hygiene(env)
    assert out["hold"] is True
    assert out["seals"] is False
    assert out["licenses_digits"] is False
    assert out["reason"] == "digit_leak"


def test_locked_digits_are_not_a_leak():
    env = {
        "ticks": [{"score_digits": "14-7", "score_vlm_locked": True, "clock_ns": 1, "frame_seq": 1}],
        "hid_on_console": True,
        "session_id": "s1",
    }
    assert unlocked_digit_leak(env) is False
    out = inspect_envelope(env)
    assert out["digit_leak"] is False
    assert out["hold"] is False


def test_truth_dest_holds():
    env = {"ticks": [], "dest_plane": "qortroller-truth", "hid_on_console": True}
    out = inspect_envelope(env)
    assert out["hold"] is True
    assert out["truth_dest"] is True
    assert out["seals"] is False


def test_export_door_unsealed_when_clean():
    view = {
        "session_id": "ncaa-half-1",
        "board_locked": True,
        "controller_bodied": False,
        "events": [
            {
                "event_id": "cpl-1",
                "t_start_ns": 100,
                "frame_seq": 4,
                "score": {"home": 14, "away": 10},
                "input": {},
            }
        ],
    }
    body = export_door(view)
    assert body["notary"]["status"] in {"UNSEALED", "HOLD"}
    assert body["door"]["live_truth"] == "DARK"
    assert body["door"]["hygiene"]["seals"] is False
    # Unlocked 14-10 must not ride the envelope; hygiene may HOLD or blank ticks.
    ticks = body.get("ticks") or []
    for t in ticks:
        if not t.get("score_vlm_locked"):
            assert t.get("score_digits") in (None, "", "□–□")
