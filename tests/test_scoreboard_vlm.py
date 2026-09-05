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


def test_default_vision_model_is_gemini_38_flash():
    assert DEFAULT_VISION_MODEL == "gemini-3.8-flash"
    cfg = LLMConfig.from_scoreboard_vlm()
    assert cfg.model == "gemini-3.8-flash"


def test_vlm_defaults_quicksilver_vision(monkeypatch):
    """Default confirm VLM is gemini-3.8-flash on ClutchBot's Quicksilver API."""
    monkeypatch.delenv("QORESENCE_SCOREBOARD_VLM_MODEL", raising=False)
    monkeypatch.delenv("QORESENCE_SCOREBOARD_VLM_BASE_URL", raising=False)
    monkeypatch.delenv("QORESENCE_CLUTCHBOT_LLM_BASE_URL", raising=False)
    cfg = LLMConfig.from_scoreboard_vlm()
    assert cfg.provider == "quicksilver"
    assert cfg.base_url.rstrip("/") == DEFAULT_BASE_URL.rstrip("/")
    assert "quicksilverpro.io" in cfg.base_url
    assert cfg.model == "gemini-3.8-flash"
    assert cfg.model == DEFAULT_VISION_MODEL
    assert cfg.model != DEFAULT_MODEL
    assert cfg.model != "muse-spark-1.3"
    assert cfg.model != "gemini-3.5-flash-lite"
    assert cfg.model != "deepseek-v4-flash"
    assert cfg.model != "deepseek-v4-flash-vision-exp"
    assert cfg.model != "qwen3.7-flash"
    ref = ScoreboardVlmReferee()
    assert ref.model == "gemini-3.8-flash"
    assert ref.model == DEFAULT_VISION_MODEL
    assert ref.base_url.rstrip("/") == DEFAULT_BASE_URL.rstrip("/")
    assert "quicksilverpro.io" in ref.base_url
    assert "api.deepseek.com" not in ref.base_url


def test_call_vlm_posts_to_quicksilver_base_url(monkeypatch):
    """Referee POST goes to ClutchBot's Quicksilver /v1, with gemini-3.8-flash + JPEG."""
    from unittest.mock import patch

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    ref.base_url = DEFAULT_BASE_URL.rstrip("/")
    ref.model = DEFAULT_VISION_MODEL
    captured: dict = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"home_score": 7, "away_score": 0, '
                                '"paused": false, "quarter": 1}'
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            }

    def _post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    with patch("requests.post", side_effect=_post):
        import numpy as np

        out = ref._call_vlm(np.zeros((96, 200, 3), dtype=np.uint8))
    assert captured["url"] == f"{DEFAULT_BASE_URL.rstrip('/')}/chat/completions"
    assert "quicksilverpro.io" in captured["url"]
    assert "api.deepseek.com" not in captured["url"]
    assert captured["json"]["model"] == "gemini-3.8-flash"
    assert captured["json"]["model"] == DEFAULT_VISION_MODEL
    assert captured["json"]["max_tokens"] == 2048
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert "thinking" not in captured["json"]
    assert captured["json"]["model"] != "gemini-3.5-flash-lite"
    content = captured["json"]["messages"][0]["content"]
    assert any(p.get("type") == "image_url" for p in content)
    assert out is not None
    assert out["home_score"] == 7
    assert out["away_score"] == 0


def test_hold_on_http_429_does_not_latch_hold():
    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._hold_on_http(429)
    assert ref.is_held() is False
    assert ref._last_http_status == 429
    assert ref._in_backoff() is True
