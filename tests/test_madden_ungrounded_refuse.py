"""Madden pause/SELECT — refuse ungrounded VLM remint; keep confirm clock fresh."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import numpy as np

from qoresence.sync.digit_integrity import digit_void_reason
from qoresence.vision.board_why import vlm_last_grounded
from qoresence.vision.confirm_ticket import (
    ConfirmTicketBook,
    get_ticket_book,
    licensed_last_confirm,
    mint_confirm_ticket,
    refresh_licensed_ticket_clock,
)
from qoresence.vision.scoreboard_extractor import (
    FootballScoreboardExtractor,
    confirm_mint_refuse,
)
from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee
from qoresence.vision.scorebug_crops import confirm_scorebug_bands
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext
from tests.test_scorebug_crop_band import _player_cu_frame


def _select_plate_parse() -> dict:
    """LIVE sit: pause/SELECT returns junk digits with clock/quarter but no wordmarks."""
    return {
        "home_score": 12,
        "away_score": 15,
        "quarter": 1,
        "clock_seconds": 15,
        "paused": True,
        "left_team": None,
        "right_team": None,
    }


def test_vlm_last_grounded_refuses_paused_select_without_wordmarks():
    assert vlm_last_grounded(_select_plate_parse()) is False


def test_confirm_mint_refuse_blocks_ungrounded_select_pair():
    book = ConfirmTicketBook()
    refuse = confirm_mint_refuse(
        home=12,
        away=15,
        game_state="menu",
        book=book,
        vlm=_select_plate_parse(),
        crop_hash="bug",
    )
    assert refuse == "vlm_ungrounded"


def test_madden_confirm_bands_exclude_postgame_top_plate():
    bands = confirm_scorebug_bands("madden_27")
    for band in bands:
        assert float(band[2]) >= 0.68


def test_madden_pause_only_frame_returns_no_confirm_crop():
    crop = ScoreboardVlmReferee._crop(
        _player_cu_frame(), game_state="menu", game_profile="madden_27"
    )
    assert crop is None


def test_ungrounded_http_200_refreshes_clock_without_remint(monkeypatch):
    book = get_ticket_book()
    book.clear()
    ticket = mint_confirm_ticket(
        session_id="s",
        clock_ns=1_000_000_000,
        home_score=13,
        away_score=31,
        crop_hash="bug",
        frame_seq=10,
        book=book,
    )
    book.put(ticket, home_team="NO", away_team="CIN")
    live_clock = {"ns": 1_000_000_000}

    monkeypatch.setattr(
        "qoresence.monitor.frame_hub.get_latest_stamp",
        lambda: {"clock_ns": live_clock["ns"], "seq": 42},
    )

    def _select_200(*_a, **_k):
        live_clock["ns"] += 2_000_000_000
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"home_score": 12, "away_score": 15, "quarter": 1, '
                            '"clock": "0:15", "paused": true}'
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        return resp

    @staticmethod
    def _fake_crop(*_a, **_k):
        crop = np.zeros((96, 200, 3), dtype=np.uint8)
        crop[:, :60] = 255
        crop[:, 140:] = 255
        return crop

    monkeypatch.setattr("requests.post", _select_200)
    monkeypatch.setattr(ScoreboardVlmReferee, "_crop", _fake_crop)

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    ref._last_call = 0.0
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[int(720 * 0.78) : int(720 * 0.93), :, 1] = 255

    ref.schedule(frame, force=True, game_state="menu", game_profile="madden_27")
    deadline = time.time() + 3.0
    while time.time() < deadline:
        with ref._lock:
            if not ref._inflight:
                break
        time.sleep(0.02)

    assert ref.get_last() is None
    last = licensed_last_confirm(book)
    assert last is not None
    assert last.ticket_id == ticket.ticket_id
    assert (last.home_score, last.away_score) == (13, 31)
    assert last.clock_ns == live_clock["ns"]
    reason = digit_void_reason(
        confirm_ticket_id=last.ticket_id,
        score_vlm_locked=True,
        ticket_crop_hash=last.crop_hash,
        live_crop_hash=last.crop_hash,
        same_seq=True,
        ticket_clock_ns=last.clock_ns,
        live_clock_ns=live_clock["ns"],
    )
    assert reason == "licensed"
    book.clear()


def test_extractor_does_not_paint_select_junk_12_15(monkeypatch):
    """Ungrounded 12-15 from pause/SELECT must not lock or paint."""
    from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

    class _FakeVlm:
        def get_last(self):
            return _select_plate_parse()

        def is_held(self):
            return False

        def is_inflight(self):
            return False

        def last_crop_refuse(self):
            return None

    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: _FakeVlm()
    )
    monkeypatch.setattr(
        "qoresence.vision.local_hud_digits.read_score_pair",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: None,
    )

    ctx = VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.MENU,
        game_profile="madden_27",
        frame_hash="madden-select-refuse",
    )
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[int(720 * 0.78) : int(720 * 0.93), :, 1] = 255
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(frame, ctx)
    assert ctx.score_vlm_locked is False
    assert not (ctx.confirm_ticket_id or "")
    assert ctx.home_score is None or (ctx.home_score, ctx.away_score) != (12, 15)


def test_refresh_licensed_ticket_clock_after_refused_200():
    book = ConfirmTicketBook()
    ticket = mint_confirm_ticket(
        session_id="s",
        clock_ns=1_000,
        home_score=7,
        away_score=0,
        crop_hash="bug",
        book=book,
    )
    book.put(ticket, home_team="KC", away_team="PHI")
    fresh = refresh_licensed_ticket_clock(clock_ns=9_000_000_000, book=book)
    assert fresh is not None
    assert fresh.ticket_id == ticket.ticket_id
    assert fresh.home_score == 7
    assert fresh.away_score == 0
    assert fresh.clock_ns == 9_000_000_000
