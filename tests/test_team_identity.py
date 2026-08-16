"""Scorebug identity: jersey color + logo stay glued to that side's team and score."""

from __future__ import annotations

from qoresence.profiles.team_identity import bind_scoreboard_sides, match_team
from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee
from qoresence.vision.visual_context import GameCategory, VisualContext


def test_smu_blue_mustang_stays_left_score():
    bound = bind_scoreboard_sides(
        left_name="SMU",
        left_color="blue",
        left_logo="mustang",
        left_score=14,
        right_name="Louisville",
        right_color="red",
        right_logo="cardinal",
        right_score=3,
        home_left=False,
    )
    assert bound["away_team"] == "SMU"
    assert bound["away_team_name"] == "SMU Mustangs"
    assert bound["away_score"] == 14
    assert bound["away_color"] == "blue"
    assert "mustang" in bound["away_logo"]
    assert bound["home_team"] == "LOU"
    assert bound["home_score"] == 3
    assert bound["home_color"] == "red"
    assert "cardinal" in bound["home_logo"]


def test_logo_and_color_win_when_name_is_swapped():
    bound = bind_scoreboard_sides(
        left_name="Louisville",  # misread
        left_color="blue",
        left_logo="horse",
        left_score=14,
        right_name="SMU",
        right_color="red",
        right_logo="cardinal bird",
        right_score=3,
        home_left=False,
    )
    assert bound["away_team"] == "SMU"
    assert bound["away_score"] == 14
    assert bound["home_team"] == "LOU"
    assert bound["home_score"] == 3


def test_match_team_uses_color_and_logo():
    smu = match_team(name="Mustangs", color="red and blue", logo="mustang head")
    lou = match_team(name="Cards", color="red", logo="cardinal")
    assert smu is not None and smu.abbr == "SMU"
    assert lou is not None and lou.abbr == "LOU"
    assert smu.abbr != lou.abbr


def test_vlm_parse_keeps_side_identity():
    raw = """{
      "home_score": 3, "away_score": 14, "home_left": false,
      "left_team": "SMU", "left_color": "blue", "left_logo": "mustang",
      "right_team": "Louisville", "right_color": "red", "right_logo": "cardinal",
      "quarter": 2, "clock": "8:12", "paused": false
    }"""
    parsed = ScoreboardVlmReferee._parse_json(raw)
    assert parsed is not None
    assert parsed["away_score"] == 14
    assert parsed["left_team"] == "SMU"
    assert parsed["left_color"] == "blue"
    assert parsed["left_logo"] == "mustang"
    assert parsed["right_team"] == "Louisville"


def test_visual_context_round_trips_colors_and_logos():
    ctx = VisualContext(
        game_category=GameCategory.FOOTBALL,
        home_team="LOU",
        home_team_name="Louisville Cardinals",
        home_color="red",
        home_logo="cardinal",
        away_team="SMU",
        away_team_name="SMU Mustangs",
        away_color="blue",
        away_logo="mustang",
    )
    d = ctx.to_dict()
    fb = d["football"]
    assert fb["home_color"] == "red"
    assert fb["away_logo"] == "mustang"
    rt = VisualContext.from_dict(d)
    assert rt.home_color == "red"
    assert rt.away_team == "SMU"
    assert rt.away_logo == "mustang"
