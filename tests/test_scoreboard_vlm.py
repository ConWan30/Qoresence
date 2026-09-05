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
    # Paint ticker (below cut) red so a leak is visible
    frame[int(h * TICKER_CUT_Y) :, :, 2] = 255
    # Paint scorebug band green
    frame[int(h * 0.78) : int(h * TICKER_CUT_Y), :, 1] = 255
    crop = ScoreboardVlmReferee._crop(frame, game_state="gameplay")
    assert crop is not None
    # No red ticker pixels in the crop
    assert int(crop[:, :, 2].max()) == 0
    assert int(crop[:, :, 1].max()) == 255


def test_vlm_menu_crop_is_pause_plate_not_ticker():
    import numpy as np

    from qoresence.vision.scoreboard_vlm import TICKER_CUT_Y, ScoreboardVlmReferee

    h, w = 100, 200
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[int(h * TICKER_CUT_Y) :, :, 2] = 255
    frame[int(h * 0.12) : int(h * 0.52), int(w * 0.22) : int(w * 0.78), 0] = 200
    crop = ScoreboardVlmReferee._crop(frame, game_state="menu")
    assert crop is not None
    assert int(crop[:, :, 2].max()) == 0
    assert int(crop[:, :, 0].max()) >= 200


def test_vlm_prompt_forbids_ticker():
    from qoresence.vision.scoreboard_vlm import _PROMPT

    assert "ticker" in _PROMPT.lower()
    assert "OTHER games" in _PROMPT


def test_vlm_prompt_ltr_spatial_contract():
    """LTR: left_* = left side of crop; never swap CAR 7 · NO 0."""
    from qoresence.vision.scoreboard_vlm import _PROMPT

    lower = _PROMPT.lower()
    assert "left_team / left_score" in lower or "left_team / left_score are" in lower
    assert "right_team / right_score" in lower or "right_team / right_score are" in lower
    assert "never swap" in lower
    assert "car" in lower and "no" in lower
    assert "never invent 0-0" in lower or "never invent 0-0 to fill" in lower
    assert "madden nfl 26" in lower
    assert "left_score" in _PROMPT
    assert "right_score" in _PROMPT


def test_vlm_parse_home_left_false():
    text = '{"home_score": 7, "away_score": 0, "home_left": false, "quarter": 1}'
    out = ScoreboardVlmReferee._parse_json(text)
    assert out is not None
    assert out["home_left"] is False


def test_vlm_parse_rejects_out_of_range():
    text = '{"home_score": 200, "away_score": 0, "quarter": 1}'
    out = ScoreboardVlmReferee._parse_json(text)
    assert out is not None
    assert out["home_score"] is None
    assert out["away_score"] == 0


def test_vlm_parse_json_chatty_english_then_object():
    text = (
        "Based on the scorebug, the home team leads. "
        '{"home_score": 14, "away_score": 0, "home_left": true, "quarter": 1}'
    )
    out = ScoreboardVlmReferee._parse_json(text)
    assert out is not None
    assert out["home_score"] == 14
    assert out["away_score"] == 0


def test_vlm_parse_json_chatty_preamble_car_bal_ltr():
    text = (
        "The scorebug shows Carolina on the left and Baltimore on the right. "
        '{"left_team": "CAR", "left_score": 14, "right_team": "BAL", "right_score": 0, '
        '"home_score": 14, "away_score": 0, "home_left": true, "quarter": 1}'
    )
    out = ScoreboardVlmReferee._parse_json(text)
    assert out is not None
    assert out["left_team"] == "CAR"
    assert out["left_score"] == 14
    assert out["right_team"] == "BAL"
    assert out["right_score"] == 0
    assert out["home_score"] == 14
    assert out["away_score"] == 0


def test_vlm_parse_json_wrapped_reply_sure_here_is_json():
    text = (
        'Sure, here is the JSON:\n'
        '{"home_score": 21, "away_score": 14, "home_left": true, "quarter": 4}\n'
        "hope that helps"
    )
    out = ScoreboardVlmReferee._parse_json(text)
    assert out is not None
    assert out["home_score"] == 21
    assert out["away_score"] == 14
    assert out["home_left"] is True
    assert out["quarter"] == 4


def test_vlm_choice_text_prefers_field_with_first_brace():
    choice = {
        "finish_reason": "stop",
        "message": {
            "content": 'Analysis mentions {noise} before the board.',
            "reasoning_content": (
                '{"left_team": "CAR", "left_score": 14, "right_team": "BAL", "right_score": 0}'
            ),
        },
    }
    text, finish = ScoreboardVlmReferee._choice_text(choice)
    assert finish == "stop"
    assert text.startswith("{")
    assert "CAR" in text


def test_vlm_choice_text_uses_content_when_brace_is_earlier():
    choice = {
        "finish_reason": "stop",
        "message": {
            "content": (
                'Preamble then {"home_score": 3, "away_score": 7, "quarter": 2}'
            ),
            "reasoning_content": "Later reasoning without json",
        },
    }
    text, _finish = ScoreboardVlmReferee._choice_text(choice)
    assert '"home_score": 3' in text


def test_vlm_call_vlm_finish_length_holds_without_parse(monkeypatch):
    import numpy as np

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"

    class _Resp:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                'Chatty preamble {"home_score": 14, "away_score": 0'
                            )
                        },
                        "finish_reason": "length",
                    }
                ]
            }

    monkeypatch.setattr("requests.post", lambda *a, **k: _Resp())
    assert ref._call_vlm(np.zeros((96, 200, 3), dtype=np.uint8)) is None


def test_default_vision_model_is_gemini_38_flash():
    assert DEFAULT_VISION_MODEL == "gemini-3.5-flash-lite"
    cfg = LLMConfig.from_scoreboard_vlm()
    assert cfg.model == "gemini-3.5-flash-lite"
