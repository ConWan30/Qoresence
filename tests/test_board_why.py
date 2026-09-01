"""Seeing-path board_why — fail-closed speech, ticket-strict overlay, VLM class."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from qoresence.mcp.server import TOOL_DEFS
from qoresence.vision.board_why import (
    BOARD_WHY_VALUES,
    classify_vlm_status,
    infer_board_why,
    refuse_to_board_why,
    vlm_status_to_board_why,
)
from qoresence.vision.scoreboard_extractor import (
    FootballScoreboardExtractor,
    garbage_lock_reason,
)
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext

DECK = Path(__file__).resolve().parents[1] / "qoresence" / "deck"
SESSION_JS = DECK / "session.js"


def test_canonical_board_why_values():
    assert "confirm_ticket" in BOARD_WHY_VALUES
    for token in (
        "unlocked",
        "no_ticket",
        "menu",
        "loading",
        "vlm_none",
        "vlm_ungrounded",
        "vlm_quota",
        "vlm_auth",
        "vlm_no_key",
        "refuse_zero_zero",
        "refuse_identity_swap",
        "refuse_suspicious",
    ):
        assert token in BOARD_WHY_VALUES


def test_refuse_mapping_matches_garbage_tokens():
    assert refuse_to_board_why("game_state", "loading") == "loading"
    assert refuse_to_board_why("game_state", "cutscene") == "loading"
    assert refuse_to_board_why("zero_zero_menu") == "menu"
    assert refuse_to_board_why("zero_zero_after_identity_swap") == "refuse_zero_zero"
    assert refuse_to_board_why("zero_zero_after_nonzero") == "refuse_zero_zero"
    assert refuse_to_board_why("identity_swap") == "refuse_identity_swap"
    assert refuse_to_board_why("suspicious_pair") == "refuse_suspicious"


def test_vlm_status_maps_to_board_why():
    assert vlm_status_to_board_why("http_429") == "vlm_quota"
    assert vlm_status_to_board_why("http_402") == "vlm_quota"
    assert vlm_status_to_board_why("http_401") == "vlm_auth"
    assert vlm_status_to_board_why("no_key") == "vlm_no_key"
    assert vlm_status_to_board_why("ungrounded") == "vlm_ungrounded"
    assert vlm_status_to_board_why("none") == "vlm_none"
    assert vlm_status_to_board_why("stale") == "vlm_none"


def test_classify_fake_429_is_http_429():
    assert (
        classify_vlm_status(has_key=True, http_status=429, last=None) == "http_429"
    )
    assert vlm_status_to_board_why("http_429") == "vlm_quota"


def test_garbage_lock_reason_still_refuses_loading():
    assert (
        garbage_lock_reason(
            home=14,
            away=7,
            home_team="DAL",
            away_team="NO",
            game_state="loading",
        )
        == "game_state"
    )
    assert refuse_to_board_why("game_state", "loading") == "loading"


def test_vlm_429_status_and_no_last(monkeypatch):
    import urllib.error

    from qoresence.vision import scoreboard_vlm

    vlm = scoreboard_vlm.ScoreboardVlmReferee()
    vlm.enabled = True
    vlm._api_key = "test_key"
    with patch("requests.post") as mock_requests:
        mock_requests.side_effect = Exception("requests unavailable")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="http://test.com",
                code=429,
                msg="Too Many Requests",
                hdrs={},
                fp=None,
            )
            frame = np.zeros((96, 160, 3), dtype=np.uint8)
            result = vlm._call_vlm(frame)
    assert result is None
    assert vlm.get_last() is None
    assert vlm._last_http_status == 429
    assert vlm.vlm_status() == "http_429"
    assert infer_board_why(vlm_status="http_429", game_state="gameplay") == "vlm_quota"


def test_extractor_429_stamps_vlm_quota_without_mint(monkeypatch):
    from qoresence.vision.scoreboard_extract_why import ensure_wrapped

    ensure_wrapped()
    monkeypatch.setenv("QORESENCE_EASY_OCR", "0")
    FootballScoreboardExtractor._stabilizer = None
    FootballScoreboardExtractor._last_board_why = "unlocked"
    extractor = FootballScoreboardExtractor()
    vlm = MagicMock()
    vlm.get_last.return_value = None
    vlm.vlm_status.return_value = "http_429"
    vlm.schedule.return_value = None
    with patch("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", return_value=vlm):
        frame = np.full((480, 640, 3), 40, dtype=np.uint8)
        frame[10:20, 10:20] = 200
        ctx = VisualContext(
            game_category=GameCategory.FOOTBALL,
            game_state=GameState.GAMEPLAY,
            game_profile="madden_27",
        )
        result = extractor.extract(frame, ctx, allow_ocr=False)
    assert result.score_vlm_locked is False
    assert not (result.confirm_ticket_id or "")
    assert result.home_score is None
    assert result.away_score is None
    assert result.board_why == "vlm_quota"
    assert result.details.get("board_why") == "vlm_quota"


def test_overlay_flag_only_is_dark_no_ticket():
    from qoresence.foundry.session_view import overlay_live_board

    view = {
        "confirmed": {"available": False, "score": None, "yard_line": None},
        "board_locked": False,
        "events": [],
    }
    out = overlay_live_board(
        view,
        {
            "score_vlm_locked": True,
            "confirm_ticket_id": "",
            "home_score": 21,
            "away_score": 14,
        },
    )
    assert out["confirmed"]["available"] is False
    assert out["confirmed"]["score"] is None
    assert out["board_why"] == "no_ticket"


def test_overlay_ticket_and_lock_paints_digits():
    from qoresence.foundry.session_view import overlay_live_board

    view = {
        "confirmed": {"available": False, "score": None, "yard_line": None},
        "board_locked": False,
        "events": [],
    }
    out = overlay_live_board(
        view,
        {
            "score_vlm_locked": True,
            "confirm_ticket_id": "deadbeef",
            "home_score": 21,
            "away_score": 14,
        },
    )
    assert out["confirmed"]["available"] is True
    assert out["confirmed"]["score"] == {"home": 21, "away": 14}
    assert out["board_why"] == "confirm_ticket"


def test_situation_passes_board_why():
    from qoresence.agents.situation_model import SituationModel
    from qoresence.core import BaseEvent, EventType, SourceLobe

    sm = SituationModel()
    sm.update(
        BaseEvent(
            session_id="test",
            clock_ns=1,
            source_lobe=SourceLobe.VISUAL,
            type=EventType.VISUAL_CONTEXT,
            payload={
                "game_state": "gameplay",
                "game_category": "football",
                "score_vlm_locked": False,
                "board_why": "vlm_quota",
            },
        )
    )
    snap = sm.to_dict()
    assert snap["board_why"] == "vlm_quota"
    assert snap["score_vlm_locked"] is False
    assert snap["confirm_ticket_id"] == ""


def test_health_snapshot_has_confirm_boolean_not_ticket_id():
    from qoresence.deck.seeing_health import install_health_patch
    from qoresence.deck.server import DeckState

    install_health_patch()

    st = DeckState()
    st.situation = {
        "game_state": "gameplay",
        "board_why": "vlm_quota",
        "score_vlm_locked": False,
        "confirm_ticket_id": "secret-ticket-id",
    }
    snap = st._snapshot_fresh()
    assert snap["board_why"] == "vlm_quota"
    assert snap["score_vlm_locked"] is False
    assert snap["has_confirm_ticket"] is True
    assert "secret-ticket-id" not in str(snap.get("has_confirm_ticket"))
    assert snap.get("confirm_ticket_id") is None
    assert "look_scale" not in snap
    assert "look_join" not in snap
    assert "look_permit_confirm" not in snap
    assert "look_refuse" not in snap


def test_session_js_maps_board_why():
    js = SESSION_JS.read_text(encoding="utf-8")
    assert "board_why" in js
    assert "Board unread (quota)" in js
    assert "Menu — board not licensed" in js
    assert "Board not licensed yet" in js
    assert "Awaiting confirmed board state" not in js or "boardWhySpeech" in js


def test_mcp_tools_list_still_has_no_session_view_or_export():
    names = {t["name"] for t in TOOL_DEFS}
    assert "civif_session_view" not in names
    assert "export_clip" not in names
