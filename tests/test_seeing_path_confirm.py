"""Seeing-path ConfirmTicket contract tests.

This test suite enforces Contract (1): ConfirmTicket mint = seeing-path only.
- source ∈ {gemini, quicksilver, easyocr_scorebug}
- NOT local_hud / chrome / menu
- HTTP 402 → unlocked (VLM get_last() is None + EasyOCR off → no confirm_ticket_id)
- license_from_tickets requires BOTH confirm_ticket_id AND score_vlm_locked
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from qoresence.agents.actuators import license_from_tickets
from qoresence.vision.confirm_ticket import (
    ConfirmTicketSourceError,
    is_seeing_source,
    mint_confirm_ticket,
    normalize_source,
)
from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor


def test_mint_with_local_hud_raises():
    """mint_confirm_ticket(..., source="local_hud") raises ConfirmTicketSourceError."""
    with pytest.raises(ConfirmTicketSourceError, match="local_hud"):
        mint_confirm_ticket(
            session_id="test",
            clock_ns=100,
            home_score=21,
            away_score=14,
            source="local_hud",
        )


def test_mint_with_chrome_raises():
    """mint_confirm_ticket(..., source="chrome") raises ConfirmTicketSourceError."""
    with pytest.raises(ConfirmTicketSourceError, match="seeing-path"):
        mint_confirm_ticket(
            session_id="test",
            clock_ns=100,
            home_score=21,
            away_score=14,
            source="chrome",
        )


def test_mint_with_menu_raises():
    """mint_confirm_ticket(..., source="menu") raises ConfirmTicketSourceError."""
    with pytest.raises(ConfirmTicketSourceError, match="seeing-path"):
        mint_confirm_ticket(
            session_id="test",
            clock_ns=100,
            home_score=21,
            away_score=14,
            source="menu",
        )


def test_mint_with_empty_source_raises():
    """mint_confirm_ticket with empty source raises."""
    with pytest.raises(ConfirmTicketSourceError, match="seeing-path"):
        mint_confirm_ticket(
            session_id="test",
            clock_ns=100,
            home_score=21,
            away_score=14,
            source="",
        )


def test_mint_with_unknown_source_raises():
    """mint_confirm_ticket(..., source="unknown") raises ConfirmTicketSourceError."""
    with pytest.raises(ConfirmTicketSourceError, match="seeing-path"):
        mint_confirm_ticket(
            session_id="test",
            clock_ns=100,
            home_score=21,
            away_score=14,
            source="unknown",
        )


def test_mint_with_hud_source_raises():
    """mint_confirm_ticket(..., source="hud") raises ConfirmTicketSourceError."""
    with pytest.raises(ConfirmTicketSourceError, match="seeing-path"):
        mint_confirm_ticket(
            session_id="test",
            clock_ns=100,
            home_score=21,
            away_score=14,
            source="hud",
        )


def test_mint_with_gemini_succeeds():
    """mint_confirm_ticket(..., source="gemini") succeeds."""
    ticket = mint_confirm_ticket(
        session_id="test",
        clock_ns=100,
        home_score=21,
        away_score=14,
        source="gemini",
    )
    assert ticket.source == "gemini"
    assert ticket.home_score == 21
    assert ticket.away_score == 14


def test_mint_with_quicksilver_succeeds():
    """mint_confirm_ticket(..., source="quicksilver") succeeds."""
    ticket = mint_confirm_ticket(
        session_id="test",
        clock_ns=100,
        home_score=21,
        away_score=14,
        source="quicksilver",
    )
    assert ticket.source == "quicksilver"


def test_mint_with_easyocr_scorebug_succeeds():
    """mint_confirm_ticket(..., source="easyocr_scorebug") succeeds."""
    ticket = mint_confirm_ticket(
        session_id="test",
        clock_ns=100,
        home_score=21,
        away_score=14,
        source="easyocr_scorebug",
    )
    assert ticket.source == "easyocr_scorebug"


def test_source_alias_gemini_scoreboard():
    """Source alias gemini_scoreboard → gemini."""
    assert normalize_source("gemini_scoreboard") == "gemini"


def test_source_alias_qs():
    """Source alias qs → quicksilver."""
    assert normalize_source("qs") == "quicksilver"


def test_source_alias_easyocr():
    """Source alias easyocr → easyocr_scorebug."""
    assert normalize_source("easyocr") == "easyocr_scorebug"


def test_source_alias_paddle():
    """Source alias paddle → easyocr_scorebug."""
    assert normalize_source("paddle") == "easyocr_scorebug"


def test_is_seeing_source_gemini():
    """is_seeing_source("gemini") returns True."""
    assert is_seeing_source("gemini") is True


def test_is_seeing_source_quicksilver():
    """is_seeing_source("quicksilver") returns True."""
    assert is_seeing_source("quicksilver") is True


def test_is_seeing_source_easyocr_scorebug():
    """is_seeing_source("easyocr_scorebug") returns True."""
    assert is_seeing_source("easyocr_scorebug") is True


def test_is_seeing_source_local_hud():
    """is_seeing_source("local_hud") returns False."""
    assert is_seeing_source("local_hud") is False


def test_is_seeing_source_chrome():
    """is_seeing_source("chrome") returns False."""
    assert is_seeing_source("chrome") is False


def test_is_seeing_source_menu():
    """is_seeing_source("menu") returns False."""
    assert is_seeing_source("menu") is False


def test_is_seeing_source_empty():
    """is_seeing_source("") returns False."""
    assert is_seeing_source("") is False


def test_is_seeing_source_none():
    """is_seeing_source(None) returns False."""
    assert is_seeing_source(None) is False


def test_http_402_unlocked(monkeypatch):
    """HTTP 402 → VLM get_last() is None + EasyOCR off → score_vlm_locked is False.
    
    This test drives 402 through _call_vlm by mocking requests.post to fail,
    then mocking urllib.request.urlopen to raise HTTPError with code 402.
    """
    # Ensure EasyOCR is off
    monkeypatch.setenv("QORESENCE_EASY_OCR", "0")
    
    from qoresence.vision import scoreboard_vlm
    import urllib.error
    
    vlm = scoreboard_vlm.ScoreboardVlmReferee()
    vlm.enabled = True
    vlm._api_key = "test_key"
    
    # Mock requests.post to fail so urllib fallback runs
    with patch("requests.post") as mock_requests:
        mock_requests.side_effect = Exception("requests unavailable")
        
        # Mock urllib.request.urlopen to raise HTTPError 402
        with patch("urllib.request.urlopen") as mock_urlopen:
            # Create HTTPError with code 402
            http_error = urllib.error.HTTPError(
                url="http://test.com",
                code=402,
                msg="Payment Required",
                hdrs={},
                fp=None,
            )
            mock_urlopen.side_effect = http_error
            
            # Call _call_vlm which should catch 402 and clear _last
            import numpy as np
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            result = vlm._call_vlm(frame)
            
            # Verify _last was cleared
            assert vlm.get_last() is None
            assert vlm._last_http_status == 402
            assert result is None


def test_kickoff_0_0_stays_unlocked_without_seeing_path(monkeypatch):
    """Kickoff 0-0 stays unlocked without seeing-path (no confirm_ticket_id).
    
    CRITICAL: ctx.home_score and ctx.away_score must be None when unlicensed.
    Glass widgetsOk stays dark by spine honesty (null scores).
    """
    monkeypatch.setenv("QORESENCE_EASY_OCR", "0")
    
    # Reset stabilizer
    FootballScoreboardExtractor._stabilizer = None
    
    extractor = FootballScoreboardExtractor()
    
    # Mock VLM to return None (402 or disabled)
    from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm
    
    with patch("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm") as mock_vlm:
        mock_vlm.return_value.get_last.return_value = None
        
        # Mock local_hud to return (35, 22) — junk
        with patch("qoresence.vision.local_hud_digits.read_score_pair") as mock_hud:
            mock_hud.return_value = (35, 22)
            
            # Extract with no VLM + HUD junk
            import numpy as np
            from qoresence.vision.visual_context import GameCategory, VisualContext
            
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            ctx = VisualContext(game_category=GameCategory.FOOTBALL)
            result = extractor.extract(frame, ctx, allow_ocr=False)
            
            # Without seeing-path, score_vlm_locked should be False
            assert not getattr(result, "score_vlm_locked", False)
            assert not getattr(result, "confirm_ticket_id", "")
            
            # CRITICAL: unlicensed HUD digits must NOT serialize
            assert result.home_score is None, "home_score must be None when unlicensed"
            assert result.away_score is None, "away_score must be None when unlicensed"


def test_qs_402_whole_session_no_junk_board_license(monkeypatch):
    """QS 402 whole session + EasyOCR off → no junk board license (35-22 never licensed).
    
    CRITICAL: ctx.home_score and ctx.away_score must be None when unlicensed.
    Glass widgetsOk stays dark by spine honesty (null scores).
    """
    monkeypatch.setenv("QORESENCE_EASY_OCR", "0")
    
    # Reset stabilizer
    FootballScoreboardExtractor._stabilizer = None
    
    extractor = FootballScoreboardExtractor()
    
    from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm
    
    with patch("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm") as mock_vlm:
        mock_vlm.return_value.get_last.return_value = None
        
        with patch("qoresence.vision.local_hud_digits.read_score_pair") as mock_hud:
            mock_hud.return_value = (35, 22)
            
            import numpy as np
            from qoresence.vision.visual_context import GameCategory, VisualContext
            
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            
            # Multiple frames, all should stay unlocked AND scores None
            for _ in range(10):
                ctx = VisualContext(game_category=GameCategory.FOOTBALL)
                result = extractor.extract(frame, ctx, allow_ocr=False)
                assert not getattr(result, "score_vlm_locked", False)
                assert not getattr(result, "confirm_ticket_id", "")
                
                # CRITICAL: unlicensed HUD digits must NOT serialize
                assert result.home_score is None, "home_score must be None when unlicensed"
                assert result.away_score is None, "away_score must be None when unlicensed"


def test_license_from_tickets_veto_with_flag_but_no_id():
    """license_from_tickets(score_vlm_locked=True, confirm_ticket_id="") is veto."""
    receipt = license_from_tickets(
        score_vlm_locked=True,
        confirm_ticket_id="",
    )
    assert receipt.kind == "veto"
    assert receipt.text == "license veto"


def test_license_from_tickets_requires_both():
    """license_from_tickets requires BOTH confirm_ticket_id AND score_vlm_locked."""
    # Only ticket, no flag
    r1 = license_from_tickets(confirm_ticket_id="deadbeef", score_vlm_locked=False)
    assert r1.kind == "veto"
    
    # Only flag, no ticket
    r2 = license_from_tickets(confirm_ticket_id="", score_vlm_locked=True)
    assert r2.kind == "veto"
    
    # Both present
    r3 = license_from_tickets(confirm_ticket_id="deadbeef", score_vlm_locked=True)
    assert r3.kind == "ticket"
    assert r3.text == "board licensed"
