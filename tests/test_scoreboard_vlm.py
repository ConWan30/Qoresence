"""Tests for gaming scoreboard VLM referee + large-digit pairing."""

from __future__ import annotations

from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor, _Token
from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee


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


def test_large_score_pair_prefers_zero_over_badge_double():
    # Giant away 20 left, giant home 0 right, tiny badge 20 far right (classic CFB pause glitch)
    tokens = [
        _Token(text="20", x=0.35, y=0.4, conf=0.95, area=0.08),
        _Token(text="0", x=0.55, y=0.4, conf=0.93, area=0.06),
        _Token(text="20", x=0.88, y=0.2, conf=0.7, area=0.005),
    ]
    pair = FootballScoreboardExtractor._parse_large_score_pair(tokens)
    # left-of-center is away, right-of-center is home
    assert pair == (0, 20)


def test_large_score_pair_home_on_left():
    # Same tokens, but the HOME team is on the left
    tokens = [
        _Token(text="20", x=0.35, y=0.4, conf=0.95, area=0.08),
        _Token(text="0", x=0.55, y=0.4, conf=0.93, area=0.06),
        _Token(text="20", x=0.88, y=0.2, conf=0.7, area=0.005),
    ]
    pair = FootballScoreboardExtractor._parse_large_score_pair(tokens, home_left=True)
    # left-of-center is home, right-of-center is away
    assert pair == (20, 0)
