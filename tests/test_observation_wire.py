"""Tests for observation wire — LAYER A spine isomorphism."""

from __future__ import annotations

import pytest


def test_observation_wire_unlabeled_when_no_visual_phase():
    """Unlabeled when no visual_phase (honest empty state)."""
    from qoresence.deck.observation_wire import build_observation_wire

    # Mock situation with frame_seq but no visual_context
    situation = {
        "frame_seq": 100,
        "clock_ns": 1000000000,
        "game_profile": "madden_27",
    }

    # Mock hid_by_seq to have a sample
    from qoresence.sync.hid_seq_line import HidSeqSample, put_sample

    sample = HidSeqSample(
        frame_seq=100,
        clock_ns=1000000000,
        buttons=("Cross",),
        hold_energy=0.5,
        edge_energy=0.5,
    )
    put_sample(sample)

    # No visual_context → visual_phase=None → mode=None → unlabeled
    obs = build_observation_wire(situation)
    assert obs is not None
    assert obs["frame_seq"] == 100
    assert obs["hid_button"] == "Cross"
    assert obs["verb"] is None  # Unlabeled (no mode)
    assert obs["mode"] is None
    assert obs["visual_phase"] is None
    assert obs["conflict"] is None


def test_observation_wire_snap_ball_on_cross_huddle_offense():
    """Cross + huddle_offense → Snap Ball (preplay_offense)."""
    from qoresence.deck.observation_wire import build_observation_wire

    # Mock visual_context with huddle_offense
    from unittest.mock import patch
    from qoresence.vision.visual_context import VisualContext

    visual_context = VisualContext(
        game_profile="madden_27",
        game_state="gameplay",
        game_title="Madden NFL 27",
        details={"visual_phase": "huddle_offense"},
    )

    situation = {
        "frame_seq": 200,
        "clock_ns": 2000000000,
        "game_profile": "madden_27",
    }

    # Mock hid_by_seq
    from qoresence.sync.hid_seq_line import HidSeqSample, put_sample

    sample = HidSeqSample(
        frame_seq=200,
        clock_ns=2000000000,
        buttons=("Cross",),
        hold_energy=0.5,
        edge_energy=0.5,
    )
    put_sample(sample)

    # Mock get_last_visual_context to return VisualContext dataclass
    with patch("qoresence.lobes.visual.get_last_visual_context") as mock_get:
        mock_get.return_value = visual_context

        obs = build_observation_wire(situation)

    assert obs is not None
    assert obs["frame_seq"] == 200
    assert obs["hid_button"] == "Cross"
    assert obs["verb"] == "Snap Ball"  # Cross in preplay_offense → Snap Ball
    assert obs["mode"] == "preplay_offense"
    assert obs["visual_phase"] == "huddle_offense"
    assert obs["game_profile"] == "madden_27"
    assert obs["conflict"] is None  # No conflict (picture and pad agree)


def test_observation_wire_cfb_l3_passing():
    """CFB L3 in passing → Throw Ball Away."""
    from qoresence.deck.observation_wire import build_observation_wire
    from unittest.mock import patch
    from qoresence.vision.visual_context import VisualContext

    visual_context = VisualContext(
        game_profile="ncaa_football_27",
        game_state="gameplay",
        game_title="NCAA College Football 27",
        details={"visual_phase": "passing"},
    )

    situation = {
        "frame_seq": 300,
        "clock_ns": 3000000000,
        "game_profile": "ncaa_football_27",
    }

    from qoresence.sync.hid_seq_line import HidSeqSample, put_sample

    sample = HidSeqSample(
        frame_seq=300,
        clock_ns=3000000000,
        buttons=("L3",),
        hold_energy=0.5,
        edge_energy=0.5,
    )
    put_sample(sample)

    with patch("qoresence.lobes.visual.get_last_visual_context") as mock_get:
        mock_get.return_value = visual_context

        obs = build_observation_wire(situation)

    assert obs is not None
    assert obs["hid_button"] == "L3"
    assert obs["verb"] == "Throw Ball Away"  # CFB L3 in passing
    assert obs["mode"] == "passing"
    assert obs["visual_phase"] == "passing"


def test_observation_wire_none_when_no_hid_sample():
    """Returns None when no HID sample at frame_seq (no fake button)."""
    from qoresence.deck.observation_wire import build_observation_wire

    situation = {
        "frame_seq": 999,
        "clock_ns": 9000000000,
        "game_profile": "madden_27",
    }

    # No HID sample at frame_seq 999 → None
    obs = build_observation_wire(situation)
    assert obs is None


def test_observation_wire_unlabeled_cross_with_unknown_profile():
    """Unlabeled Cross when profile unknown: hid_button present, verb/mode None."""
    from qoresence.deck.observation_wire import build_observation_wire

    # No game_profile in situation
    situation = {
        "frame_seq": 400,
        "clock_ns": 4000000000,
    }

    from qoresence.sync.hid_seq_line import HidSeqSample, put_sample

    sample = HidSeqSample(
        frame_seq=400,
        clock_ns=4000000000,
        buttons=("Cross",),
        hold_energy=0.5,
        edge_energy=0.5,
    )
    put_sample(sample)

    # No visual context
    from unittest.mock import patch
    with patch("qoresence.lobes.visual.get_last_visual_context") as mock_get:
        mock_get.return_value = None

        obs = build_observation_wire(situation)

    # MUST emit observation with hid_button even when unlabeled
    assert obs is not None
    assert obs["frame_seq"] == 400
    assert obs["hid_button"] == "Cross"
    assert obs["verb"] is None  # Unlabeled (no game profile)
    assert obs["mode"] is None
    assert obs["visual_phase"] is None
    assert obs["game_profile"] is None
    assert obs["conflict"] is None


def test_observation_wire_visual_context_dataclass_instance():
    """VisualContext dataclass instance (not dict) still emits unlabeled HID."""
    from qoresence.deck.observation_wire import build_observation_wire
    from unittest.mock import patch
    from qoresence.vision.visual_context import VisualContext

    # VisualContext without visual_phase in details
    visual_context = VisualContext(
        game_profile="madden_27",
        game_state="gameplay",
        game_title="Madden NFL 27",
        # No visual_phase in details - should still work
    )

    situation = {
        "frame_seq": 500,
        "clock_ns": 5000000000,
        "game_profile": "madden_27",
    }

    from qoresence.sync.hid_seq_line import HidSeqSample, put_sample

    sample = HidSeqSample(
        frame_seq=500,
        clock_ns=5000000000,
        buttons=("Triangle",),
        hold_energy=0.5,
        edge_energy=0.5,
    )
    put_sample(sample)

    with patch("qoresence.lobes.visual.get_last_visual_context") as mock_get:
        mock_get.return_value = visual_context

        obs = build_observation_wire(situation)

    # Should emit observation with hid_button even without visual_phase
    assert obs is not None
    assert obs["frame_seq"] == 500
    assert obs["hid_button"] == "Triangle"
    # No visual_phase means no mode lookup, so unlabeled
    assert obs["verb"] is None
    assert obs["mode"] is None
    assert obs["visual_phase"] is None
    assert obs["game_profile"] == "madden_27"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
