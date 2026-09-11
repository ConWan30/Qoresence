"""MomentScorer ClutchFeed soft lines — Madden NFL abbrev gate."""

from __future__ import annotations

from qoresence.agents.moment_scorer import MomentScorer
from qoresence.agents.situation_model import SituationState


def test_live_football_soft_blanks_psu_on_madden():
    scorer = MomentScorer(wp_enabled=False, clip_model_path="/tmp/__nonexistent__.json")
    state = SituationState(
        game_profile="madden_27",
        game_state="gameplay",
        home_team="NO",
        away_team="PSU",
        home_score=0,
        away_score=14,
        quarter=1,
    )
    line = scorer._live_football_soft(state)
    assert "PSU" not in line
    assert "14" in line
    assert "0" in line


def test_live_football_soft_keeps_det_no_on_madden():
    scorer = MomentScorer(wp_enabled=False, clip_model_path="/tmp/__nonexistent__.json")
    state = SituationState(
        game_profile="madden_27",
        game_state="gameplay",
        home_team="NO",
        away_team="DET",
        home_score=0,
        away_score=14,
        quarter=1,
    )
    line = scorer._live_football_soft(state)
    assert "DET" in line
    assert "NO" in line
    assert "PSU" not in line
    assert "14" in line
    assert "0" in line


def test_live_football_soft_cfb_may_speak_psu():
    scorer = MomentScorer(wp_enabled=False, clip_model_path="/tmp/__nonexistent__.json")
    state = SituationState(
        game_profile="ncaa_football_27",
        game_state="gameplay",
        home_team="OSU",
        away_team="PSU",
        home_score=0,
        away_score=14,
        quarter=1,
    )
    line = scorer._live_football_soft(state)
    assert "PSU" in line
    assert "14" in line
