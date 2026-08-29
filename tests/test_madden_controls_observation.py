"""Tests for Madden 27 control observation plane.

Regression tests lock in the fail-closed observation invariants:
1. Cross + preplay_offense → Snap Ball
2. Cross + running → Stiff Arm
3. No mode → verb None
4. Lookup reads hid_by_seq[seq], never HID[now]
"""

from __future__ import annotations

import time

import numpy as np


class TestMaddenControlLookup:
    """Test EA Madden 27 control legend loading and lookup."""

    def test_load_madden_controls(self):
        """Madden 27 controls data must load successfully."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        # Should have 10 modes
        assert len(lookup._controls) == 10
        assert "preplay_offense" in lookup._controls
        assert "running" in lookup._controls
        assert "defense_engaged" in lookup._controls

    def test_cross_preplay_offense_snap_ball(self):
        """Cross + preplay_offense → Snap Ball."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        verb = lookup.lookup_verb("Cross", "preplay_offense")
        assert verb == "Snap Ball"

    def test_cross_running_stiff_arm(self):
        """Cross + running → Stiff Arm."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        verb = lookup.lookup_verb("Cross", "running")
        assert verb == "Stiff Arm"

    def test_cross_defense_engaged_switch_player(self):
        """Defense Engaged writes Switch Player as X (Cross is DualSense name)."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        verb = lookup.lookup_verb("Cross", "defense_engaged")
        assert verb == "Switch Player"

    def test_no_mode_returns_none(self):
        """No mode → verb None (fail-closed)."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        verb = lookup.lookup_verb("Cross", None)
        assert verb is None

    def test_unknown_mode_returns_none(self):
        """Unknown mode → verb None (fail-closed)."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        verb = lookup.lookup_verb("Cross", "not_a_real_mode")
        assert verb is None

    def test_multiple_verbs_comma_separated(self):
        """L1 in ball_in_air has multiple verbs (DEF + OFF)."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        verb = lookup.lookup_verb("L1", "ball_in_air")
        assert "DEF Defensive Assist" in verb
        assert "OFF Spectacular Catch" in verb


class TestModeDetection:
    """Test fail-closed mode detection from visual_context."""

    def test_non_madden_profile_returns_none(self):
        """Only Madden 27 profiles are mapped (fail-closed)."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        mode = lookup.map_game_state_to_mode(
            {"game_state": "gameplay", "game_profile": "ncaa_football_27"}
        )
        assert mode is None

    def test_menu_state_returns_none(self):
        """Only gameplay state is mapped (fail-closed)."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        mode = lookup.map_game_state_to_mode({"game_state": "menu", "game_profile": "madden_27"})
        assert mode is None

    def test_madden_gameplay_fail_closed_for_now(self):
        """Madden gameplay → fail-closed (None) until preplay signals integrated."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        mode = lookup.map_game_state_to_mode(
            {"game_state": "gameplay", "game_profile": "madden_27"}
        )
        # Hypothesis: preplay vs in-play may already exist, but not integrated yet
        # For now, fail-closed returns None
        assert mode is None


class TestObserveButtonPress:
    """Test observation of button presses from hid_by_seq."""

    def test_observe_reads_hid_by_seq_not_hid_now(self):
        """observe_button_press reads hid_by_seq[seq], never HID[now]."""
        from qoresence.monitor.frame_hub import get_frame_hub
        from qoresence.observation.madden_controls import observe_button_press
        from qoresence.sync.hid_seq_line import get_hid_seq_line
        from qoresence.sync.input_ring import set_hold

        hub = get_frame_hub()
        line = get_hid_seq_line()
        hub.clear()
        line.clear()

        # Publish frame with Cross pressed at seq=42
        t0 = time.monotonic_ns()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        set_hold(clock_ns=t0, r2=0.0, l2=0.0, lx=0.0, ly=0.0, buttons=("Cross",))
        hub.publish(frame, clock_ns=t0, seq=42)

        # Now change HID[now] to Circle
        set_hold(clock_ns=t0 + int(50e6), r2=0.0, l2=0.0, lx=0.0, ly=0.0, buttons=("Circle",))

        # Observe at seq=42 should get Cross from hid_by_seq[42], not Circle from HID[now]
        obs = observe_button_press(frame_seq=42, clock_ns=t0)
        assert len(obs) == 1
        assert obs[0].hid_button == "Cross"

    def test_no_mode_emits_observation_with_none_verb(self):
        """No mode → still emit observation, but verb is None."""
        from qoresence.monitor.frame_hub import get_frame_hub
        from qoresence.observation.madden_controls import observe_button_press
        from qoresence.sync.hid_seq_line import get_hid_seq_line
        from qoresence.sync.input_ring import set_hold

        hub = get_frame_hub()
        line = get_hid_seq_line()
        hub.clear()
        line.clear()

        t0 = time.monotonic_ns()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        set_hold(clock_ns=t0, r2=0.0, l2=0.0, lx=0.0, ly=0.0, buttons=("Square",))
        hub.publish(frame, clock_ns=t0, seq=10)

        # No visual_context → mode is None
        obs = observe_button_press(frame_seq=10, clock_ns=t0)
        assert len(obs) == 1
        assert obs[0].hid_button == "Square"
        assert obs[0].verb is None
        assert obs[0].mode is None

    def test_observe_hid_edge_single_button(self):
        """observe_hid_edge emits one observation for a single button edge."""
        from qoresence.observation.madden_controls import observe_hid_edge

        obs = observe_hid_edge(
            frame_seq=5,
            clock_ns=12345,
            button_name="Triangle",
            visual_context=None,
        )
        assert obs.frame_seq == 5
        assert obs.clock_ns == 12345
        assert obs.hid_button == "Triangle"
        assert obs.verb is None  # no mode
        assert obs.mode is None

    def test_observation_to_dict(self):
        """ControlObservation serializes to dict."""
        from qoresence.observation.madden_controls import ControlObservation

        obs = ControlObservation(
            frame_seq=42,
            clock_ns=999,
            hid_button="Cross",
            verb="Snap Ball",
            mode="preplay_offense",
        )
        d = obs.to_dict()
        assert d["frame_seq"] == 42
        assert d["clock_ns"] == 999
        assert d["hid_button"] == "Cross"
        assert d["verb"] == "Snap Ball"
        assert d["mode"] == "preplay_offense"
        assert d["source"] == "ea_ps_controls_hub"
        assert d["plane"] == "qoresence-observation"


class TestObserveStaysOffGrabThread:
    """Observation plane must never block grab thread."""

    def test_observe_never_called_from_streamer_grab_loop(self):
        """observe_button_press is observation plane only — never on grab."""
        # This is enforced by architecture: observe_button_press is not called
        # from qoresence/lobes/streamer.py grab loop. It only reads hid_by_seq,
        # which is populated by FrameHub subscriber (off grab).
        # This test is a documentation placeholder.
        pass


class TestPhaseMapsToSheet:
    """visual_phase + gameplay + madden profile selects a sheet."""

    def test_huddle_offense_maps_preplay(self):
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        mode = lookup.map_game_state_to_mode(
            {
                "game_state": "gameplay",
                "game_profile": "madden_27",
                "details": {"visual_phase": "huddle_offense"},
            }
        )
        assert mode == "preplay_offense"

    def test_observe_hid_edge_labeled_when_phase_present(self):
        from qoresence.observation.madden_controls import observe_hid_edge

        obs = observe_hid_edge(
            frame_seq=7,
            clock_ns=1,
            button_name="Cross",
            visual_context={
                "game_state": "gameplay",
                "game_profile": "madden_27",
                "details": {"visual_phase": "huddle_offense"},
            },
        )
        assert obs.mode == "preplay_offense"
        assert obs.verb == "Snap Ball"
        assert obs.to_dict()["plane"] == "qoresence-observation"

    def test_ball_in_air_triangle_keeps_both_verbs(self):
        from qoresence.observation.madden_controls import MaddenControlLookup

        verb = MaddenControlLookup().lookup_verb("Triangle", "ball_in_air")
        assert "OFF Aggressive Catch" in verb
        assert "DEF Ball Hawk" in verb

    def test_ncaa_profile_never_selects_madden_sheet(self):
        from qoresence.observation.madden_controls import MaddenControlLookup

        mode = MaddenControlLookup().map_game_state_to_mode(
            {
                "game_state": "gameplay",
                "game_profile": "ncaa_football_27",
                "details": {"visual_phase": "huddle_offense"},
            }
        )
        assert mode is None


class TestGrabLoopIsolation:
    def test_streamer_does_not_import_madden_controls(self):
        from pathlib import Path

        src = Path("qoresence/lobes/streamer.py").read_text(encoding="utf-8")
        assert "madden_controls" not in src
        assert "observe_button_press" not in src
        assert "observe_hid_edge" not in src
