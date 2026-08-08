"""Tests for gaming scoreboard VLM referee + large-digit pairing."""

from __future__ import annotations

from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor, _Token
from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee


def test_vlm_parse_json_20_0():
    text = '{"home_score": 20, "away_score": 0, "quarter": 3, "clock": "4:51", "down": 2, "yards_to_go": 10, "play_clock": 24, "paused": true}'
    out = ScoreboardVlmReferee._parse_json(text)
    assert out is not None
    assert out["home_score"] == 20
    assert out["away_score"] == 0
    assert out["quarter"] == 3
    assert out["clock_seconds"] == 4 * 60 + 51
    assert out["paused"] is True


def test_vlm_parse_rejects_out_of_range():
    text = '{"home_score": 200, "away_score": 0, "quarter": 1}'
    out = ScoreboardVlmReferee._parse_json(text)
    assert out is not None
    assert out["home_score"] is None
    assert out["away_score"] == 0


def test_large_score_pair_prefers_zero_over_badge_double():
    # Giant 20 left, giant 0 right, tiny badge 20 far right (classic CFB pause glitch)
    tokens = [
        _Token(text="20", x=0.35, y=0.4, conf=0.95, area=0.08),
        _Token(text="0", x=0.55, y=0.4, conf=0.93, area=0.06),
        _Token(text="20", x=0.88, y=0.2, conf=0.7, area=0.005),
    ]
    pair = FootballScoreboardExtractor._parse_large_score_pair(tokens)
    assert pair == (20, 0)
