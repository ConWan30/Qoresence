"""Preplay Subs/Preplay stick HUD must not trip #220 pause refuse."""

from __future__ import annotations

from qoresence.vision.board_why import (
    normalize_vlm_paused_flag,
    vlm_has_scorebug_wordmarks,
    vlm_last_grounded,
    vlm_looks_like_live_ingame_hud,
)
from qoresence.vision.scoreboard_extractor import confirm_mint_refuse
from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee
from qoresence.vision.confirm_ticket import ConfirmTicketBook
from tests.test_madden_ungrounded_refuse import _select_plate_parse


def _preplay_nyj_ten_parse() -> dict:
    """LIVE sit: NYJ 7 - TEN 35, Q3 2nd&15, wordmarks, VLM wrongly paused=true."""
    return {
        "home_score": 35,
        "away_score": 7,
        "home_left": False,
        "left_team": "NYJ",
        "right_team": "TEN",
        "left_score": 7,
        "right_score": 35,
        "quarter": 3,
        "down": 2,
        "yards_to_go": 15,
        "clock_seconds": 742,
        "paused": True,
        "visible_control": {"button": "Cross", "glyph": None, "prompt": "Preplay"},
    }


def test_preplay_live_hud_has_wordmarks_and_down_distance():
    parse = _preplay_nyj_ten_parse()
    assert vlm_has_scorebug_wordmarks(parse) is True
    assert vlm_looks_like_live_ingame_hud(parse) is True


def test_normalize_clears_paused_for_preplay_wordmarks():
    parse = _preplay_nyj_ten_parse()
    norm = normalize_vlm_paused_flag(parse)
    assert norm is not None
    assert norm["paused"] is False


def test_vlm_last_grounded_accepts_preplay_with_wordmarks_despite_paused():
    assert vlm_last_grounded(_preplay_nyj_ten_parse()) is True


def test_confirm_mint_refuse_allows_preplay_menu_with_wordmarks():
    book = ConfirmTicketBook()
    refuse = confirm_mint_refuse(
        home=35,
        away=7,
        home_team="TEN",
        away_team="NYJ",
        game_state="menu",
        book=book,
        vlm=_preplay_nyj_ten_parse(),
        crop_hash="preplay-bug",
    )
    assert refuse is None


def test_select_without_wordmarks_still_refuses():
    book = ConfirmTicketBook()
    refuse = confirm_mint_refuse(
        home=12,
        away=15,
        game_state="menu",
        book=book,
        vlm=_select_plate_parse(),
        crop_hash="select-plate",
    )
    assert refuse == "vlm_ungrounded"


def test_parse_json_normalizes_preplay_paused():
    text = (
        '{"home_score": 7, "away_score": 35, "home_left": false, '
        '"left_team": "NYJ", "right_team": "TEN", "quarter": 3, '
        '"down": 2, "yards_to_go": 15, "clock": "12:22", "paused": true, '
        '"visible_control": {"button": "Cross", "prompt": "Preplay"}}'
    )
    parsed = ScoreboardVlmReferee._parse_json(text)
    assert parsed is not None
    assert parsed["paused"] is False
    assert parsed["left_team"] == "NYJ"
    assert parsed["right_team"] == "TEN"


def test_normalize_keeps_true_pause_select_without_wordmarks():
    parse = _select_plate_parse()
    norm = normalize_vlm_paused_flag(parse)
    assert norm is not None
    assert norm["paused"] is True
    assert vlm_last_grounded(parse) is False
