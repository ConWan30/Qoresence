"""Play-phrase DELETED — classify/emit always OFF; no DualSense chatter."""
from __future__ import annotations

from qoresence.sync.play_phrase import (
    PLAY_PHRASE_ENABLED,
    classify_phrase,
    phrase_payload,
    reset_phrase_sticky,
)


def test_play_phrase_hard_off():
    assert PLAY_PHRASE_ENABLED is False


def test_classify_always_off():
    reset_phrase_sticky()
    p, conf = classify_phrase(
        game_state="gameplay",
        r2=0.9,
        prev_r2=0.9,
        hold_fresh=True,
        video_age_s=0.04,
    )
    assert p == "OFF"
    assert conf == 0.0


def test_phrase_payload_always_off():
    assert phrase_payload("SPRINT", 0.9) == {
        "phrase": "OFF",
        "phrase_conf": 0.0,
        "phrase_live": False,
    }


def test_never_emits_live_lattice_words():
    for kwargs in (
        {"game_state": "menu", "r2": 0.9, "hold_fresh": True, "video_age_s": 0.05},
        {"game_state": "gameplay", "r2": 0.92, "prev_r2": 0.9, "hold_fresh": True, "video_age_s": 0.04},
        {"game_state": "gameplay", "r2": 0.0, "prev_r2": 0.9, "video_age_s": 0.04},
    ):
        p, _ = classify_phrase(**kwargs)
        assert p not in {"IDLE", "HUDDLE", "SNAP", "SPRINT", "CUT", "RELEASE"}
        assert p == "OFF"
