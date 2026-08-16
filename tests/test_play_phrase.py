"""Play-phrase classifier (no hardware)."""

from __future__ import annotations

from qoresence.sync.play_phrase import classify_phrase, note_game_state


def test_menu_idle_even_with_r2():
    note_game_state("menu")
    phrase, _ = classify_phrase(
        game_state="menu", r2=0.9, hold_fresh=True, video_age_s=0.05
    )
    assert phrase == "IDLE"


def test_sprint_on_fresh_r2_hold():
    phrase, conf = classify_phrase(
        game_state="gameplay",
        r2=0.92,
        prev_r2=0.90,
        hold_fresh=True,
        video_age_s=0.04,
    )
    assert phrase == "SPRINT"
    assert conf > 0.5


def test_snap_needs_onset_and_motion():
    phrase, _ = classify_phrase(
        game_state="gameplay",
        r2=0.8,
        prev_r2=0.0,
        r2_onset_edge=True,
        motion=4.0,
        hold_fresh=True,
        video_age_s=0.03,
    )
    assert phrase == "SNAP"
    no_motion, _ = classify_phrase(
        game_state="gameplay",
        r2=0.8,
        prev_r2=0.0,
        r2_onset_edge=True,
        motion=0.0,
        hold_fresh=True,
        video_age_s=0.03,
    )
    assert no_motion == "SPRINT"


def test_release_on_falling_r2():
    phrase, _ = classify_phrase(
        game_state="gameplay",
        r2=0.0,
        prev_r2=0.9,
        video_age_s=0.04,
        hold_fresh=False,
    )
    assert phrase == "RELEASE"


def test_cut_needs_stick_and_motion():
    phrase, _ = classify_phrase(
        game_state="gameplay",
        left=0.7,
        motion=3.0,
        video_age_s=0.04,
        hold_fresh=True,
    )
    assert phrase == "CUT"


def test_huddle_in_gameplay_idle():
    phrase, _ = classify_phrase(
        game_state="gameplay",
        r2=0.0,
        left=0.0,
        video_age_s=0.04,
        hold_fresh=False,
    )
    assert phrase == "HUDDLE"
