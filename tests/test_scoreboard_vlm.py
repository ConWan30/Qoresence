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


def test_vlm_watchdog_clears_stale_inflight():
    """Inflight watchdog clears _inflight if VLM thread is stale (>16s).
    
    Regression test for 2026-08-29: if a VLM thread hangs or _inflight sticks,
    the next tick should be able to run after the HTTP timeout (~14s) + 2s buffer.
    """
    import numpy as np
    import time

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test-key"  # Enable scheduling
    
    h, w = 720, 1280
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[int(h * 0.78) : int(h * 0.93), :, 1] = 255
    
    # Manually set inflight + old timestamp
    with ref._lock:
        ref._inflight = True
        ref._inflight_since = time.time() - 20.0  # 20s ago (stale)
    
    # schedule should clear stale inflight and allow a new call
    ref.schedule(frame, force=True, game_state="gameplay", game_profile="cfb_27")
    
    # Check that inflight was cleared and reset
    with ref._lock:
        # After watchdog clears and new schedule runs, inflight is True again (new call)
        assert ref._inflight is True, "Watchdog should clear stale, then schedule sets new inflight"
        # The new inflight_since should be recent (< 2s)
        assert (time.time() - ref._inflight_since) < 2.0, "New inflight_since should be recent"


def test_situation_model_maps_cfb_title_to_cfb_profile():
    """SituationModel corrects game_profile when title is CFB but profile is madden.
    
    Regression test for 2026-08-29: /health showed game_profile=madden_27 with
    game_title='EA SPORTS College Football 27'. The situation model must re-map
    the profile based on title so published situation has cfb_27 not madden_27.
    """
    from qoresence.agents.situation_model import SituationModel
    from qoresence.core import BaseEvent, EventType, SourceLobe
    
    model = SituationModel()
    
    # Create a visual_context event with CFB title but madden profile
    event = BaseEvent(
        source_lobe=SourceLobe.VISUAL,
        type=EventType.VISUAL_CONTEXT,
        payload={
            "game_state": "menu",
            "game_profile": "madden_27",
            "game_title": "EA SPORTS College Football 27",
            "confidence": 0.9,
        },
        clock_ns=1_000_000_000,
        session_head_ns=0,
    )
    
    model.update(event)
    
    # The published state should have cfb_27, not madden_27
    assert model.state.game_profile == "cfb_27", "CFB title must map to cfb_27 profile"
    assert model.state.game_title == "EA SPORTS College Football 27"
