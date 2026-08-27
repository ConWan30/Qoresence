"""Tests for visual_phase → sheet mapper (observation plane).

Regression tests lock in fail-closed mapping invariants:
1. huddle_offense + madden_27 → preplay_offense
2. running + madden_27 → running
3. No visual_phase → None
4. Wrong game profile → None
5. CFB vs Madden sheet differences (blocking vs blocking_mechanics)
"""

from __future__ import annotations


class TestVisualPhaseToSheet:
    """Test visual_phase → sheet key mapping."""

    def test_huddle_offense_madden_preplay_offense(self):
        """huddle_offense + madden_27 → preplay_offense."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("huddle_offense", "madden_27")
        assert sheet == "preplay_offense"

    def test_huddle_defense_madden_preplay_defense(self):
        """huddle_defense + madden_27 → preplay_defense."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("huddle_defense", "madden_27")
        assert sheet == "preplay_defense"

    def test_snap_madden_preplay_offense(self):
        """snap + madden_27 → preplay_offense (snap is preplay)."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("snap", "madden_27")
        assert sheet == "preplay_offense"

    def test_running_madden_running(self):
        """running + madden_27 → running."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("running", "madden_27")
        assert sheet == "running"

    def test_passing_madden_passing(self):
        """passing + madden_27 → passing."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("passing", "madden_27")
        assert sheet == "passing"

    def test_ball_in_air_madden_ball_in_air(self):
        """ball_in_air + madden_27 → ball_in_air."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("ball_in_air", "madden_27")
        assert sheet == "ball_in_air"

    def test_coverage_madden_defensive_coverage(self):
        """coverage + madden_27 → defensive_coverage."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("coverage", "madden_27")
        assert sheet == "defensive_coverage"

    def test_defense_pursuit_madden_defense_pursuit(self):
        """defense_pursuit + madden_27 → defense_pursuit."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("defense_pursuit", "madden_27")
        assert sheet == "defense_pursuit"

    def test_defense_engaged_madden_defense_engaged(self):
        """defense_engaged + madden_27 → defense_engaged."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("defense_engaged", "madden_27")
        assert sheet == "defense_engaged"

    def test_blocking_madden_blocking(self):
        """blocking + madden_27 → blocking."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("blocking", "madden_27")
        assert sheet == "blocking"

    def test_player_locked_receiver_madden_player_locked_receiver(self):
        """player_locked_receiver + madden_27 → player_locked_receiver."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("player_locked_receiver", "madden_27")
        assert sheet == "player_locked_receiver"

    def test_unknown_phase_returns_none(self):
        """Unknown phase → None (fail-closed)."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("unknown_phase", "madden_27")
        assert sheet is None

    def test_none_phase_returns_none(self):
        """None phase → None (fail-closed)."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet(None, "madden_27")
        assert sheet is None

    def test_none_profile_returns_none(self):
        """None profile → None (fail-closed)."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("running", None)
        assert sheet is None

    def test_wrong_profile_returns_none(self):
        """Wrong game profile → None (fail-closed)."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("running", "call_of_duty")
        assert sheet is None


class TestCfbSheetMapping:
    """Test CFB 27 specific sheet mappings."""

    def test_huddle_offense_cfb_preplay_offense(self):
        """huddle_offense + cfb_27 → preplay_offense."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("huddle_offense", "cfb_27")
        assert sheet == "preplay_offense"

    def test_running_cfb_running(self):
        """running + cfb_27 → running."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("running", "cfb_27")
        assert sheet == "running"

    def test_coverage_cfb_defensive_coverage_mechanics(self):
        """coverage + cfb_27 → defensive_coverage_mechanics (differs from Madden)."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        cfb_sheet = map_visual_phase_to_sheet("coverage", "cfb_27")
        madden_sheet = map_visual_phase_to_sheet("coverage", "madden_27")

        assert cfb_sheet == "defensive_coverage_mechanics"
        assert madden_sheet == "defensive_coverage"
        assert cfb_sheet != madden_sheet

    def test_blocking_cfb_blocking_mechanics(self):
        """blocking + cfb_27 → blocking_mechanics (differs from Madden)."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        cfb_sheet = map_visual_phase_to_sheet("blocking", "cfb_27")
        madden_sheet = map_visual_phase_to_sheet("blocking", "madden_27")

        assert cfb_sheet == "blocking_mechanics"
        assert madden_sheet == "blocking"
        assert cfb_sheet != madden_sheet

    def test_cfb_aliases_recognized(self):
        """CFB / college / NCAA profile aliases all work."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        for profile in ["cfb_27", "college_football_27", "ncaa_football_27"]:
            sheet = map_visual_phase_to_sheet("huddle_offense", profile)
            assert sheet == "preplay_offense"


class TestGetVisualPhaseFromContext:
    """Test extracting visual_phase from visual_context payload."""

    def test_extract_from_details_visual_phase(self):
        """Preferred: visual_context.details.visual_phase."""
        from qoresence.observation.sheet_from_picture import get_visual_phase_from_context

        ctx = {"details": {"visual_phase": "huddle_offense"}}
        phase = get_visual_phase_from_context(ctx)
        assert phase == "huddle_offense"

    def test_extract_from_top_level_visual_phase(self):
        """Fallback: visual_context.visual_phase."""
        from qoresence.observation.sheet_from_picture import get_visual_phase_from_context

        ctx = {"visual_phase": "running"}
        phase = get_visual_phase_from_context(ctx)
        assert phase == "running"

    def test_prefer_details_over_top_level(self):
        """Prefer details.visual_phase over top-level."""
        from qoresence.observation.sheet_from_picture import get_visual_phase_from_context

        ctx = {"visual_phase": "running", "details": {"visual_phase": "passing"}}
        phase = get_visual_phase_from_context(ctx)
        assert phase == "passing"

    def test_empty_context_returns_none(self):
        """Empty context → None."""
        from qoresence.observation.sheet_from_picture import get_visual_phase_from_context

        phase = get_visual_phase_from_context({})
        assert phase is None

    def test_none_context_returns_none(self):
        """None context → None."""
        from qoresence.observation.sheet_from_picture import get_visual_phase_from_context

        phase = get_visual_phase_from_context(None)
        assert phase is None


class TestMapContextToSheet:
    """Test end-to-end visual_context → sheet mapping."""

    def test_madden_huddle_offense_via_details(self):
        """Madden + huddle_offense via details → preplay_offense."""
        from qoresence.observation.sheet_from_picture import map_context_to_sheet

        ctx = {
            "game_state": "gameplay",
            "game_profile": "madden_27",
            "details": {"visual_phase": "huddle_offense"},
        }
        sheet = map_context_to_sheet(ctx)
        assert sheet == "preplay_offense"

    def test_cfb_running_via_top_level(self):
        """CFB + running via top-level → running."""
        from qoresence.observation.sheet_from_picture import map_context_to_sheet

        ctx = {
            "game_state": "gameplay",
            "game_profile": "cfb_27",
            "visual_phase": "running",
        }
        sheet = map_context_to_sheet(ctx)
        assert sheet == "running"

    def test_no_visual_phase_returns_none(self):
        """No visual_phase → None (fail-closed)."""
        from qoresence.observation.sheet_from_picture import map_context_to_sheet

        ctx = {"game_state": "gameplay", "game_profile": "madden_27"}
        sheet = map_context_to_sheet(ctx)
        assert sheet is None

    def test_wrong_game_profile_returns_none(self):
        """Wrong game profile → None (fail-closed)."""
        from qoresence.observation.sheet_from_picture import map_context_to_sheet

        ctx = {
            "game_state": "gameplay",
            "game_profile": "call_of_duty",
            "visual_phase": "running",
        }
        sheet = map_context_to_sheet(ctx)
        assert sheet is None


class TestMaddenControlsIntegration:
    """Test MaddenControlLookup integration with sheet mapper."""

    def test_cross_huddle_offense_snap_ball(self):
        """Cross + huddle_offense → Snap Ball."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        ctx = {
            "game_state": "gameplay",
            "game_profile": "madden_27",
            "details": {"visual_phase": "huddle_offense"},
        }
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode == "preplay_offense"
        verb = lookup.lookup_verb("Cross", mode)
        assert verb == "Snap Ball"

    def test_cross_running_stiff_arm(self):
        """Cross + running → Stiff Arm."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        ctx = {
            "game_state": "gameplay",
            "game_profile": "madden_27",
            "visual_phase": "running",
        }
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode == "running"
        verb = lookup.lookup_verb("Cross", mode)
        assert verb == "Stiff Arm"

    def test_no_visual_phase_returns_none_verb(self):
        """No visual_phase → None verb (fail-closed)."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        ctx = {"game_state": "gameplay", "game_profile": "madden_27"}
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode is None
        verb = lookup.lookup_verb("Cross", mode)
        assert verb is None


class TestCfbControlsIntegration:
    """Test CfbControlLookup integration with sheet mapper."""

    def test_cross_huddle_offense_snap_ball(self):
        """Cross + huddle_offense → Snap Ball."""
        from qoresence.observation.cfb_controls import CfbControlLookup

        lookup = CfbControlLookup()
        ctx = {
            "game_state": "gameplay",
            "game_profile": "cfb_27",
            "details": {"visual_phase": "huddle_offense"},
        }
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode == "preplay_offense"
        verb = lookup.lookup_verb("Cross", mode)
        assert verb == "Snap Ball"

    def test_cross_running_stiff_arm(self):
        """Cross + running → Stiff Arm."""
        from qoresence.observation.cfb_controls import CfbControlLookup

        lookup = CfbControlLookup()
        ctx = {
            "game_state": "gameplay",
            "game_profile": "cfb_27",
            "visual_phase": "running",
        }
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode == "running"
        verb = lookup.lookup_verb("Cross", mode)
        assert verb == "Stiff Arm"

    def test_l3_passing_throw_ball_away(self):
        """L3 + passing → Throw Ball Away (CFB uses L3, Madden uses R3)."""
        from qoresence.observation.cfb_controls import CfbControlLookup
        from qoresence.observation.madden_controls import MaddenControlLookup

        cfb_lookup = CfbControlLookup()
        madden_lookup = MaddenControlLookup()

        cfb_ctx = {
            "game_state": "gameplay",
            "game_profile": "cfb_27",
            "visual_phase": "passing",
        }
        madden_ctx = {
            "game_state": "gameplay",
            "game_profile": "madden_27",
            "visual_phase": "passing",
        }

        cfb_mode = cfb_lookup.map_game_state_to_mode(cfb_ctx)
        madden_mode = madden_lookup.map_game_state_to_mode(madden_ctx)

        assert cfb_mode == "passing"
        assert madden_mode == "passing"

        cfb_l3 = cfb_lookup.lookup_verb("L3", cfb_mode)
        madden_r3 = madden_lookup.lookup_verb("R3", madden_mode)

        assert cfb_l3 == "Throw Ball Away"
        assert madden_r3 == "Throw Ball Away"

    def test_cross_defense_engaged_differs_madden_cfb(self):
        """Defense Engaged Cross → CFB Disengage vs Madden Switch Player."""
        from qoresence.observation.cfb_controls import CfbControlLookup
        from qoresence.observation.madden_controls import MaddenControlLookup

        cfb_lookup = CfbControlLookup()
        madden_lookup = MaddenControlLookup()

        cfb_ctx = {
            "game_state": "gameplay",
            "game_profile": "cfb_27",
            "visual_phase": "defense_engaged",
        }
        madden_ctx = {
            "game_state": "gameplay",
            "game_profile": "madden_27",
            "visual_phase": "defense_engaged",
        }

        cfb_mode = cfb_lookup.map_game_state_to_mode(cfb_ctx)
        madden_mode = madden_lookup.map_game_state_to_mode(madden_ctx)

        assert cfb_mode == "defense_engaged"
        assert madden_mode == "defense_engaged"

        cfb_verb = cfb_lookup.lookup_verb("Cross", cfb_mode)
        madden_verb = madden_lookup.lookup_verb("Cross", madden_mode)

        assert cfb_verb == "Disengage"
        assert madden_verb == "Switch Player"
        assert cfb_verb != madden_verb

    def test_no_visual_phase_returns_none_verb(self):
        """No visual_phase → None verb (fail-closed)."""
        from qoresence.observation.cfb_controls import CfbControlLookup

        lookup = CfbControlLookup()
        ctx = {"game_state": "gameplay", "game_profile": "cfb_27"}
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode is None
        verb = lookup.lookup_verb("Cross", mode)
        assert verb is None
