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


def test_vlm_gameplay_crop_excludes_ticker():
    import numpy as np

    from qoresence.vision.scoreboard_vlm import TICKER_CUT_Y, ScoreboardVlmReferee

    h, w = 100, 200
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[int(h * TICKER_CUT_Y) :, :, 2] = 255
    frame[int(h * 0.78) : int(h * TICKER_CUT_Y), :, 1] = 255
    crop = ScoreboardVlmReferee._crop(frame, game_state="gameplay")
    assert crop is not None
    assert int(crop[:, :, 2].max()) == 0
    assert int(crop[:, :, 1].max()) == 255


def test_default_vision_model_is_gemini_38_flash():
    assert DEFAULT_VISION_MODEL == "gemini-3.5-flash-lite"
    cfg = LLMConfig.from_scoreboard_vlm()
    assert cfg.model == "gemini-3.5-flash-lite"


def test_vlm_defaults_quicksilver_vision(monkeypatch):
    """Default confirm VLM is gemini-3.5-flash-lite on ClutchBot's Quicksilver API."""
    monkeypatch.delenv("QORESENCE_SCOREBOARD_VLM_MODEL", raising=False)
    monkeypatch.delenv("QORESENCE_SCOREBOARD_VLM_BASE_URL", raising=False)
    monkeypatch.delenv("QORESENCE_CLUTCHBOT_LLM_BASE_URL", raising=False)
    cfg = LLMConfig.from_scoreboard_vlm()
    assert cfg.provider == "quicksilver"
    assert cfg.base_url.rstrip("/") == DEFAULT_BASE_URL.rstrip("/")
    assert "quicksilverpro.io" in cfg.base_url
    assert cfg.model == "gemini-3.5-flash-lite"
    assert cfg.model == DEFAULT_VISION_MODEL
    assert cfg.model != DEFAULT_MODEL
    assert cfg.model != "muse-spark-1.3"
    assert cfg.model != "gemini-3.8-flash"
    assert cfg.model != "deepseek-v4-flash"
    assert cfg.model != "deepseek-v4-flash-vision-exp"
    assert cfg.model != "qwen3.7-flash"
    ref = ScoreboardVlmReferee()
    assert ref.model == "gemini-3.5-flash-lite"
    assert ref.model == DEFAULT_VISION_MODEL
    assert ref.base_url.rstrip("/") == DEFAULT_BASE_URL.rstrip("/")
    assert "quicksilverpro.io" in ref.base_url
    assert "api.deepseek.com" not in ref.base_url
