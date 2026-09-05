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


def test_vlm_parse_json_markdown_fence():
    text = '```json\n{"home_score": 7, "away_score": 3, "quarter": 2}\n```'
    out = ScoreboardVlmReferee._parse_json(text)
    assert out is not None
    assert out["home_score"] == 7
    assert out["away_score"] == 3
    assert out["quarter"] == 2


def test_vlm_parse_json_english_only_returns_none():
    assert ScoreboardVlmReferee._parse_json("No scorebug visible on this frame.") is None


def test_vlm_parse_json_truncated_object_returns_none():
    assert ScoreboardVlmReferee._parse_json('Here is the board {"home_score": 14') is None


def test_vlm_parse_json_skips_invalid_brace_in_prose():
    text = 'The {team} marker shows {"home_score": 3, "away_score": 7, "quarter": 1}'
    out = ScoreboardVlmReferee._parse_json(text)
    assert out is not None
    assert out["home_score"] == 3
    assert out["away_score"] == 7


def test_vlm_zero_zero_object_still_not_licensed_lock():
    from qoresence.vision.confirm_ticket import (
        ConfirmTicketBook,
        mint_confirm_ticket,
        ticket_is_licensed_lock,
    )

    out = ScoreboardVlmReferee._parse_json('{"home_score": 0, "away_score": 0, "quarter": 1}')
    assert out is not None
    assert out["home_score"] == 0
    assert out["away_score"] == 0
    book = ConfirmTicketBook()
    ticket = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=0,
        away_score=0,
        crop_hash="abc",
        book=book,
    )
    assert ticket_is_licensed_lock(ticket) is False


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
        session_id="test",
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


def test_vlm_model_flag_override(monkeypatch):
    monkeypatch.setenv("QORESENCE_SCOREBOARD_VLM_MODEL", "gemini-3.6-flash")
    cfg = LLMConfig.from_scoreboard_vlm()
    assert cfg.model == "gemini-3.6-flash"
    ref = ScoreboardVlmReferee()
    assert ref.model == "gemini-3.6-flash"
    assert ref.base_url.rstrip("/") == DEFAULT_BASE_URL.rstrip("/")


def test_vlm_missing_key_fail_closed(monkeypatch, tmp_path):
    """No clutchbot / Quicksilver key → VLM disabled, no invented board."""
    monkeypatch.chdir(tmp_path)
    for k in (
        "QORESENCE_SCOREBOARD_VLM_API_KEY",
        "QORESENCE_CLUTCHBOT_LLM_API_KEY",
        "QORESENCE_CLUTCHBOT_LLM_API_KEY_FILE",
        "QORESENCE_SCOREBOARD_VLM_KEY_FILE",
        "QUICKSILVER_API_KEY",
        "QUICKSILVERPRO_API_KEY",
        "QUICKSILVER_API_KEY_FILE",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "QORESENCE_DEEPSEEK_API_KEY",
        "QORESENCE_VISUAL_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("QORESENCE_SCOREBOARD_VLM", "1")
    ref = ScoreboardVlmReferee()
    assert ref.enabled is False
    assert ref.get_last() is None
    assert ref._api_key is None


def test_http_401_fail_closed():
    """HTTP 401 → HOLD seeing-path, no last-good board."""
    import urllib.error
    from unittest.mock import patch

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"

    with patch("requests.post") as mock_requests:
        mock_requests.side_effect = Exception("requests unavailable")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="http://test.com",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=None,
            )
            import numpy as np

            result = ref._call_vlm(np.zeros((96, 200, 3), dtype=np.uint8))
            assert result is None
            assert ref.get_last() is None
            assert ref._last_http_status == 401
            assert ref.is_held() is True


def test_call_vlm_posts_to_quicksilver_base_url(monkeypatch):
    """Referee POST goes to ClutchBot's Quicksilver /v1, with gemini-3.5-flash-lite + JPEG."""
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
    assert captured["json"]["model"] == "gemini-3.5-flash-lite"
    assert captured["json"]["model"] == DEFAULT_VISION_MODEL
    assert captured["json"]["max_tokens"] == 2048
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert "thinking" not in captured["json"]
    assert captured["json"]["model"] != "gemini-3.8-flash"
    content = captured["json"]["messages"][0]["content"]
    assert any(p.get("type") == "image_url" for p in content)
    assert out is not None
    assert out["home_score"] == 7
    assert out["away_score"] == 0


def test_infer_vlm_source_gemini_on_quicksilver():
    assert infer_vlm_source("gemini-3.5-flash-lite", DEFAULT_BASE_URL) == "gemini"
    assert infer_vlm_source("gemini-3.5-flash-lite", DEFAULT_BASE_URL) == "gemini"
    assert infer_vlm_source("qwen3.7-flash", DEFAULT_BASE_URL) == "quicksilver"
    assert infer_vlm_source("deepseek-v4-flash", DEFAULT_BASE_URL) == "quicksilver"
    assert infer_vlm_source("deepseek-v4-flash-vision-exp", "https://api.deepseek.com") == "deepseek"


def test_http_400_holds_without_urllib_retry_and_redacts_body(caplog):
    """HTTP 400 HOLDs last_confirm, does not urllib-retry, logs body without secrets."""
    import logging
    from unittest.mock import patch

    import numpy as np

    from qoresence.vision.scoreboard_vlm import _safe_http_body

    leaked = (
        "model not found sk-secretTOKEN123 Bearer abc.def "
        "api_key=sk-other data:image/jpeg;base64,/9j/xxxx"
    )
    assert "sk-secretTOKEN123" not in _safe_http_body(leaked)
    assert "Bearer abc.def" not in _safe_http_body(leaked)
    assert "/9j/xxxx" not in _safe_http_body(leaked)

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    posts = {"n": 0}

    class _Resp:
        status_code = 400
        text = leaked

    def _post(*_a, **_k):
        posts["n"] += 1
        return _Resp()

    crop = np.zeros((96, 200, 3), dtype=np.uint8)
    with caplog.at_level(logging.WARNING):
        with patch("requests.post", side_effect=_post):
            with patch("urllib.request.urlopen") as urlopen:
                out = ref._call_vlm(crop)
                urlopen.assert_not_called()
    assert out is None
    assert posts["n"] == 1
    assert ref.is_held() is True
    assert ref.get_last() is None
    assert ref._last_http_status == 400
    assert "sk-secretTOKEN123" not in caplog.text
    assert "Bearer abc.def" not in caplog.text
    assert "HOLD seeing-path" in caplog.text

    with patch.object(ref, "_call_vlm") as call:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[int(720 * 0.78) : int(720 * 0.93), :, 1] = 255
        ref.schedule(frame, force=True, reason="score_changed")
        call.assert_not_called()


def test_visual_lobe_skips_post_after_scoreboard_hold(monkeypatch):
    from unittest.mock import MagicMock

    import numpy as np

    from qoresence.core import VisualConfig
    from qoresence.lobes.visual import VLMClient

    held = MagicMock()
    held.is_held.return_value = True
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: held
    )
    client = VLMClient(VisualConfig(api_key="test_key"))
    client._session = MagicMock()
    out = client.analyze_frame_raw(np.zeros((64, 64, 3), dtype=np.uint8), "prompt")
    assert out is None
    client._session.post.assert_not_called()


def test_hold_402_drops_last_confirm_and_blanks_glass():
    """Seeing-path HOLD drops last_confirm / score_vlm_locked. Fail-closed empty."""
    from qoresence.agents.situation_model import SituationModel
    from qoresence.vision.confirm_ticket import get_ticket_book, mint_confirm_ticket

    book = get_ticket_book()
    book.clear()
    ticket = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=7,
        away_score=0,
        crop_hash="crop-ok",
        book=book,
    )
    book.put(ticket, home_team="DAL", away_team="NO")
    assert book.latest() is ticket
    assert book.mismatch()["last_confirm"]["ticket_id"] == ticket.ticket_id

    sm = SituationModel()
    sm._state.score_vlm_locked = True
    sm._state.confirm_ticket_id = ticket.ticket_id
    sm._state.home_score = 7
    sm._state.away_score = 0

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._hold_on_http(402)
    assert ref.is_held() is True
    assert book.latest() is None
    assert book.mismatch()["last_confirm"] is None

    singleton = None
    try:
        from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

        singleton = get_scoreboard_vlm()
        singleton._held = True
        snap = sm.to_dict()
        assert snap["score_vlm_locked"] is False
        assert snap["confirm_ticket_id"] == ""
        assert snap["home_score"] is None
        assert snap["away_score"] is None
    finally:
        if singleton is not None:
            singleton._held = False
            singleton._backoff_until = 0.0
        book.clear()


def test_stuck_zero_zero_last_confirm_does_not_paint():
    """A 0-0 last_confirm with empty crop_hash must not keep the glass at 0-0."""
    from qoresence.agents.situation_model import SituationModel
    from qoresence.deck.seeing_health import attach_board_health
    from qoresence.vision.confirm_ticket import get_ticket_book, mint_confirm_ticket

    book = get_ticket_book()
    book.clear()
    stuck = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=0,
        away_score=0,
        crop_hash="",
        book=book,
    )
    book.put(stuck, home_team="NO", away_team="DET")
    sm = SituationModel()
    sm._state.score_vlm_locked = True
    sm._state.confirm_ticket_id = stuck.ticket_id
    sm._state.home_score = 0
    sm._state.away_score = 0
    try:
        snap = sm.to_dict()
        assert snap["score_vlm_locked"] is False
        assert snap["home_score"] is None
        assert snap["away_score"] is None
        assert book.mismatch()["last_confirm"] is None
        health = attach_board_health(
            {},
            {
                "score_vlm_locked": True,
                "confirm_ticket_id": stuck.ticket_id,
                "board_why": "confirm_ticket",
            },
        )
        assert health["score_vlm_locked"] is False
        assert health["has_confirm_ticket"] is False
    finally:
        book.clear()


def test_default_gameplay_interval_is_six_seconds():
    import os

    from qoresence.vision.scoreboard_vlm import _GAMEPLAY_INTERVAL_S, _HOLD_HTTP

    assert _GAMEPLAY_INTERVAL_S == float(
        os.environ.get("QORESENCE_SCOREBOARD_VLM_INTERVAL", "6.0")
    )
    assert 429 not in _HOLD_HTTP
    assert {400, 401, 402} <= set(_HOLD_HTTP)


def test_http_429_soft_backoff_not_permanent_hold(monkeypatch, caplog):
    """HTTP 429 cools down; is_held stays false so ConfirmTicket can mint after wait."""
    import logging
    from unittest.mock import patch

    import numpy as np

    from qoresence.vision import scoreboard_vlm

    times = {"t": 1_000.0}
    monkeypatch.setattr(scoreboard_vlm, "_QUOTA_BACKOFF_S", 60.0)
    monkeypatch.setattr(scoreboard_vlm.time, "time", lambda: times["t"])

    ref = scoreboard_vlm.ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"

    class _Resp:
        status_code = 429
        text = ""

    crop = np.zeros((96, 200, 3), dtype=np.uint8)
    with caplog.at_level(logging.WARNING):
        with patch("requests.post", return_value=_Resp()):
            with patch("urllib.request.urlopen") as urlopen:
                out = ref._call_vlm(crop)
                urlopen.assert_not_called()
    assert out is None
    assert ref.is_held() is False
    assert ref.get_last() is None
    assert ref._last_http_status == 429
    assert ref.vlm_status() == "http_429"
    assert ref._backoff_until == 1_060.0
    assert ref._in_backoff() is True
    assert "quota backoff" in caplog.text
    assert "HOLD seeing-path" not in caplog.text

    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[int(720 * 0.78) : int(720 * 0.93), :, 1] = 255
    with patch.object(ref, "_crop") as crop_fn:
        ref.schedule(frame, force=True, reason="score_changed")
        crop_fn.assert_not_called()

    with patch("requests.post") as post:
        assert ref._call_vlm(crop) is None
        post.assert_not_called()

    times["t"] = 1_060.1
    assert ref._in_backoff() is False
    assert ref.is_held() is False
    called = []
    monkeypatch.setattr(ref, "_crop", lambda *a, **k: called.append("crop") or crop)
    monkeypatch.setattr(ref, "_call_vlm", lambda _c: None)
    ref.schedule(frame, force=True, reason="score_changed")
    assert called == ["crop"]
    assert ref.is_held() is False


def test_hold_on_http_429_does_not_latch_hold():
    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._hold_on_http(429)
    assert ref.is_held() is False
    assert ref._last_http_status == 429
    assert ref._in_backoff() is True
