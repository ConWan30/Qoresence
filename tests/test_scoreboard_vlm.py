"""Tests for gaming scoreboard VLM referee + large-digit pairing."""

from __future__ import annotations

from qoresence.agents.llm_client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_VISION_MODEL,
    LLMConfig,
)
from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor, _Token
from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee, infer_vlm_source


def test_vlm_parse_json_20_0():
    text = '{"home_score": 20, "away_score": 0, "home_left": true, "quarter": 3, "clock": "4:51", "down": 2, "yards_to_go": 10, "play_clock": 24, "paused": true}'
    out = ScoreboardVlmReferee._parse_json(text)
    assert out is not None
    assert out["home_score"] == 20
    assert out["away_score"] == 0
    assert out["home_left"] is True
    assert out["quarter"] == 3
    assert out["clock_seconds"] == 4 * 60 + 51
    assert out["paused"] is True
