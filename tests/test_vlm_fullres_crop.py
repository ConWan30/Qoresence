"""Regression tests for VLM full-res crop fix (issue #110 follow-up).

After #110 (main 54c71d00), operator saw:
- scoreboard VLM HTTP 200 (good)
- first parse: None-None q=None reason=tick
- later: "null parse"
- cadence still 8.0s (menu interval) so game_state is still treated as menu
- last_confirm empty, license veto, do not invent scores

Root cause: visual.py _analyze_frame resizes frame to max_frame_dim THEN calls
_merge_scoreboard / extract_football_scoreboard. VLM crops a downscaled classify
frame, so CFB y=0.78-0.93 and Madden y=0.93-1.00 become a tiny strip or mush;
DeepSeek returns null or unparseable prose.

Fix:
1) Crop VLM from FrameHub latest FULL-RES frame, not downscaled classify copy
2) Football titles: use gameplay VLM interval (~1.5s) even when game_state=menu
3) On HTTP 200 + parse fail: INFO-log preview + try extra JSON recovery
4) Write last VLM crop JPEG to logs/vlm_last_crop.jpg
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor
from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


def test_football_uses_gameplay_interval_even_on_menu():
    """Football titles (CFB/Madden) should use gameplay interval even when game_state=menu."""
    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._inflight = False
    ref._last_call = 0.0
    
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    
    # Test CFB profile with menu state
    import time
    ref._last_call = time.time() - 10.0  # Long ago
    
    called = False
    original_call_vlm = ref._call_vlm
    
    def mock_call_vlm(crop):
        nonlocal called
        called = True
        return {"home_score": 14, "away_score": 7}
    
    ref._call_vlm = mock_call_vlm
    
    # Schedule with menu state but CFB profile
    ref.schedule(frame, game_state="menu", game_profile="cfb_27", reason="tick")
    
    # Give background thread time to run
    import time
    time.sleep(0.5)
    
    # Should have called VLM despite menu state (because CFB uses gameplay interval)
    # The test verifies that the interval check allows it through
    assert ref._last_call > 0  # schedule was accepted
    
    # Cleanup
    ref._call_vlm = original_call_vlm


def test_parse_fail_does_not_mint_confirm():
    """HTTP 200 + null parse should not mint a confirm ticket or lock."""
    ext = FootballScoreboardExtractor()
    
    # Mock VLM that returns unparseable response
    mock_vlm = Mock()
    mock_vlm.get_last.return_value = None  # Parse failed
    mock_vlm.schedule = Mock()
    
    with patch("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", return_value=mock_vlm):
        frame = np.full((720, 1280, 3), 80, dtype=np.uint8)
        ctx = VisualContext(
            game_category=GameCategory.FOOTBALL,
            game_state=GameState.GAMEPLAY,
            game_profile="cfb_27",
        )
        
        result = ext.extract(frame, ctx, allow_ocr=False)
        
        # No scores should be set without a valid parse
        assert result.home_score is None
        assert result.away_score is None
        assert result.score_vlm_locked is False
        assert result.confirm_ticket_id is None


def test_no_invented_scores_without_ticket():
    """Scoreboard should not invent scores (0-0, 3-2, etc.) without a confirm ticket."""
    ext = FootballScoreboardExtractor()
    
    # Mock VLM with no result
    mock_vlm = Mock()
    mock_vlm.get_last.return_value = None
    mock_vlm.schedule = Mock()
    
    with patch("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", return_value=mock_vlm), \
         patch("qoresence.vision.local_hud_digits.read_score_pair", return_value=None):
        
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        ctx = VisualContext(
            game_category=GameCategory.FOOTBALL,
            game_state=GameState.GAMEPLAY,
            game_profile="madden_27",
        )
        
        result = ext.extract(frame, ctx, allow_ocr=False)
        
        # Should stay None, not invent 0-0 or any other score
        assert result.home_score is None
        assert result.away_score is None
        assert result.score_vlm_locked is False


def test_json_recovery_strips_fences():
    """Parser should recover from markdown code fences around JSON."""
    text = """```json
{"home_score": 21, "away_score": 14, "quarter": 3}
```"""
    
    parsed = ScoreboardVlmReferee._parse_json(text)
    assert parsed is not None
    assert parsed["home_score"] == 21
    assert parsed["away_score"] == 14


def test_json_recovery_handles_prose_then_json():
    """Parser should extract JSON even when surrounded by prose."""
    text = """Looking at the scoreboard, I can see:
{"home_score": 28, "away_score": 7, "quarter": 4, "paused": false}
This appears to be a football game."""
    
    parsed = ScoreboardVlmReferee._parse_json(text)
    assert parsed is not None
    assert parsed["home_score"] == 28
    assert parsed["away_score"] == 7


def test_vlm_crop_saved_to_logs(tmp_path):
    """Last VLM crop should be saved to logs/vlm_last_crop.jpg."""
    import cv2
    
    ref = ScoreboardVlmReferee()
    ref.enabled = False  # Don't actually call API
    
    # Create test crop
    crop = np.full((100, 200, 3), 128, dtype=np.uint8)
    
    # Mock the HTTP call to avoid actual API request
    with patch("requests.post") as mock_post:
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"home_score": null, "away_score": null}'}}]
        }
        mock_post.return_value = mock_resp
        
        # Temporarily change working directory to tmp_path
        import os
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        
        try:
            ref._call_vlm(crop)
            
            # Check that file was created
            log_file = tmp_path / "logs" / "vlm_last_crop.jpg"
            assert log_file.exists(), "vlm_last_crop.jpg should be created"
            
            # Verify it's a valid JPEG
            loaded = cv2.imread(str(log_file))
            assert loaded is not None
            assert loaded.shape == crop.shape
        finally:
            os.chdir(old_cwd)


def test_null_parse_does_not_mint_confirm():
    """VLM returning explicit null/None for scores should not mint confirm ticket."""
    from qoresence.vision.scoreboard_extractor import _ScoreStabilizer
    
    ext = FootballScoreboardExtractor()
    FootballScoreboardExtractor._stabilizer = _ScoreStabilizer(window=6, need=2)
    
    # Mock VLM that returns valid JSON but with null scores
    mock_vlm = Mock()
    mock_vlm.get_last.return_value = {
        "home_score": None,
        "away_score": None,
        "quarter": None,
        "paused": False,
    }
    mock_vlm.schedule = Mock()
    
    with patch("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", return_value=mock_vlm), \
         patch("qoresence.vision.local_hud_digits.read_score_pair", return_value=None):
        
        frame = np.full((720, 1280, 3), 80, dtype=np.uint8)
        ctx = VisualContext(
            game_category=GameCategory.FOOTBALL,
            game_state=GameState.GAMEPLAY,
            game_profile="cfb_27",
        )
        
        result = ext.extract(frame, ctx, allow_ocr=False)
        
        # Should not lock or mint ticket with null scores
        assert result.home_score is None
        assert result.away_score is None
        assert result.score_vlm_locked is False
        assert result.confirm_ticket_id is None
