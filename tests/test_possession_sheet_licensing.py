"""Tests for possession-based sheet licensing (offense vs defense from football symbol).

Regression tests lock in the sheet-from-picture possession invariants:
1. possession_side null → no offense/defense phase (fail-closed)
2. possession_side + home_left → offense or defense
3. R2 button shows different verbs for offense vs defense sheets
4. No possession symbol → raw hid only, no verb
"""

from __future__ import annotations


class TestPossessionInference:
    """Test inferring offense/defense from scoreboard possession mark."""

    def test_possession_null_returns_none(self):
        """possession_side null → None (fail-closed)."""
        from qoresence.observation.sheet_from_picture import infer_offense_defense_from_possession

        result = infer_offense_defense_from_possession(
            {"possession_side": None, "home_left": False},
            is_home_team=True,
        )
        assert result is None

    def test_home_left_none_returns_none(self):
        """home_left null → None (fail-closed)."""
        from qoresence.observation.sheet_from_picture import infer_offense_defense_from_possession

        result = infer_offense_defense_from_possession(
            {"possession_side": "left", "home_left": None},
            is_home_team=True,
        )
        assert result is None

    def test_home_has_possession_left_side(self):
        """Home team on left + possession left → offense."""
        from qoresence.observation.sheet_from_picture import infer_offense_defense_from_possession

        result = infer_offense_defense_from_possession(
            {"possession_side": "left", "home_left": True},
            is_home_team=True,
        )
        assert result == "offense"

    def test_home_has_possession_right_side(self):
        """Home team on right + possession right → offense."""
        from qoresence.observation.sheet_from_picture import infer_offense_defense_from_possession

        result = infer_offense_defense_from_possession(
            {"possession_side": "right", "home_left": False},
            is_home_team=True,
        )
        assert result == "offense"

    def test_home_defense_away_has_possession_left(self):
        """Home team on right + possession left → defense."""
        from qoresence.observation.sheet_from_picture import infer_offense_defense_from_possession

        result = infer_offense_defense_from_possession(
            {"possession_side": "left", "home_left": False},
            is_home_team=True,
        )
        assert result == "defense"

    def test_home_defense_away_has_possession_right(self):
        """Home team on left + possession right → defense."""
        from qoresence.observation.sheet_from_picture import infer_offense_defense_from_possession

        result = infer_offense_defense_from_possession(
            {"possession_side": "right", "home_left": True},
            is_home_team=True,
        )
        assert result == "defense"

    def test_away_team_offense(self):
        """Away team controlling + possession on away side → offense."""
        from qoresence.observation.sheet_from_picture import infer_offense_defense_from_possession

        # Away team is on left (home_left=False means away is left, home is right)
        # Possession on left → away has ball
        result = infer_offense_defense_from_possession(
            {"possession_side": "left", "home_left": False},
            is_home_team=False,
        )
        assert result == "offense"

    def test_away_team_defense(self):
        """Away team controlling + possession on home side → defense."""
        from qoresence.observation.sheet_from_picture import infer_offense_defense_from_possession

        # Away team is on left, home on right
        # Possession on right → home has ball, away is defense
        result = infer_offense_defense_from_possession(
            {"possession_side": "right", "home_left": False},
            is_home_team=False,
        )
        assert result == "defense"


class TestOffenseDefenseSheetMapping:
    """Test that offense/defense phases map to correct sheets."""

    def test_offense_phase_maps_to_preplay_offense(self):
        """offense phase → preplay_offense sheet."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("offense", "madden_27")
        assert sheet == "preplay_offense"

    def test_defense_phase_maps_to_preplay_defense(self):
        """defense phase → preplay_defense sheet."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("defense", "madden_27")
        assert sheet == "preplay_defense"

    def test_cfb_offense_phase_maps_to_preplay_offense(self):
        """CFB offense phase → preplay_offense sheet."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("offense", "cfb_27")
        assert sheet == "preplay_offense"

    def test_cfb_defense_phase_maps_to_preplay_defense(self):
        """CFB defense phase → preplay_defense sheet."""
        from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

        sheet = map_visual_phase_to_sheet("defense", "cfb_27")
        assert sheet == "preplay_defense"


class TestR2VerbDifferentiation:
    """Test that R2 shows different verbs for offense vs defense sheets."""

    def test_r2_offense_show_play_art(self):
        """R2 + offense phase → Show Play Art (Madden)."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        ctx = {
            "game_state": "gameplay",
            "game_profile": "madden_27",
            "details": {"visual_phase": "offense"},
        }
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode == "preplay_offense"
        verb = lookup.lookup_verb("R2", mode)
        assert "Show Play Art" in verb

    def test_r2_defense_xfactor_vision(self):
        """R2 + defense phase → X-Factor Vision (Madden)."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        ctx = {
            "game_state": "gameplay",
            "game_profile": "madden_27",
            "details": {"visual_phase": "defense"},
        }
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode == "preplay_defense"
        verb = lookup.lookup_verb("R2", mode)
        assert "X-Factor Vision" in verb

    def test_r2_cfb_offense_show_playart(self):
        """R2 + offense phase → Show Playart (CFB)."""
        from qoresence.observation.cfb_controls import CfbControlLookup

        lookup = CfbControlLookup()
        ctx = {
            "game_state": "gameplay",
            "game_profile": "cfb_27",
            "details": {"visual_phase": "offense"},
        }
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode == "preplay_offense"
        verb = lookup.lookup_verb("R2", mode)
        assert "Show Playart" in verb

    def test_r2_cfb_defense_show_playart(self):
        """R2 + defense phase → Show Playart (CFB)."""
        from qoresence.observation.cfb_controls import CfbControlLookup

        lookup = CfbControlLookup()
        ctx = {
            "game_state": "gameplay",
            "game_profile": "cfb_27",
            "details": {"visual_phase": "defense"},
        }
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode == "preplay_defense"
        verb = lookup.lookup_verb("R2", mode)
        assert "Show Playart" in verb


class TestScoreboardVLMPossession:
    """Test that scoreboard VLM extracts possession_side."""

    def test_parse_json_with_possession_left(self):
        """VLM JSON with possession_side: left."""
        from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee

        ref = ScoreboardVlmReferee()
        json_text = """{
            "home_score": 17,
            "away_score": 14,
            "home_left": false,
            "left_team": "DAL",
            "right_team": "PHI",
            "quarter": 3,
            "clock": "8:42",
            "possession_side": "left",
            "paused": false
        }"""
        result = ref._parse_json(json_text)
        assert result is not None
        assert result["possession_side"] == "left"
        assert result["home_score"] == 17
        assert result["away_score"] == 14

    def test_parse_json_with_possession_right(self):
        """VLM JSON with possession_side: right."""
        from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee

        ref = ScoreboardVlmReferee()
        json_text = """{
            "home_score": 21,
            "away_score": 20,
            "home_left": true,
            "possession_side": "right",
            "paused": false
        }"""
        result = ref._parse_json(json_text)
        assert result is not None
        assert result["possession_side"] == "right"

    def test_parse_json_with_possession_null(self):
        """VLM JSON with possession_side: null (fail-closed)."""
        from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee

        ref = ScoreboardVlmReferee()
        json_text = """{
            "home_score": 7,
            "away_score": 3,
            "possession_side": null,
            "paused": false
        }"""
        result = ref._parse_json(json_text)
        assert result is not None
        assert result["possession_side"] is None

    def test_parse_json_possession_missing(self):
        """VLM JSON without possession_side → None (fail-closed)."""
        from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee

        ref = ScoreboardVlmReferee()
        json_text = """{
            "home_score": 14,
            "away_score": 10,
            "paused": false
        }"""
        result = ref._parse_json(json_text)
        assert result is not None
        assert result["possession_side"] is None


class TestNoSheetFallback:
    """Test that missing possession → raw hid only, no verb."""

    def test_no_visual_phase_no_verb(self):
        """No visual_phase (no possession) → None verb."""
        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        ctx = {
            "game_state": "gameplay",
            "game_profile": "madden_27",
            # No details.visual_phase
        }
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode is None
        verb = lookup.lookup_verb("R2", mode)
        assert verb is None

    def test_possession_null_no_sheet_no_verb(self):
        """possession_side null → no phase → no verb."""
        from qoresence.observation.sheet_from_picture import infer_offense_defense_from_possession

        phase = infer_offense_defense_from_possession(
            {"possession_side": None, "home_left": False},
            is_home_team=True,
        )
        assert phase is None

        from qoresence.observation.madden_controls import MaddenControlLookup

        lookup = MaddenControlLookup()
        ctx = {
            "game_state": "gameplay",
            "game_profile": "madden_27",
            "details": {"visual_phase": phase} if phase else {},
        }
        mode = lookup.map_game_state_to_mode(ctx)
        assert mode is None
        verb = lookup.lookup_verb("R2", mode)
        assert verb is None
