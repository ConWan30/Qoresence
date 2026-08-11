"""Tests for local scoreboard OCR extraction."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


def test_extract_leaves_non_football_unchanged():
    extractor = FootballScoreboardExtractor()
    ctx = VisualContext(game_category=GameCategory.UNKNOWN)
    frame = (255 * (cv2.getGaussianKernel(100, 10) @ cv2.getGaussianKernel(100, 10).T)).astype(
        "uint8"
    )
    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    result = extractor.extract(frame, ctx)
    assert result is ctx
    assert result.game_category == GameCategory.UNKNOWN


def test_extract_handles_tiny_frame():
    extractor = FootballScoreboardExtractor()
    ctx = VisualContext(game_category=GameCategory.FOOTBALL)
    frame = np.full((10, 10, 3), 255, dtype=np.uint8)
    result = extractor.extract(frame, ctx)
    assert result.game_category == GameCategory.FOOTBALL


def test_extractor_parses_eye_verify():
    """If the captured verification frame exists, expect the known scoreboard."""
    path = Path("logs/eye_verify.jpg")
    if not path.exists():
        pytest.skip("logs/eye_verify.jpg not available")

    # This test needs a working scoreboard reader. Skip if VLM is disabled and
    # OCR is not available. Conftest disables OCR by default; we do not override
    # that here because EasyOCR/PaddleOCR models may not be downloaded.
    import os

    from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

    # Reset any stale VLM result from earlier tests — each test should start
    # from a clean state and not inherit a previous frame's scoreboard.
    get_scoreboard_vlm()._last = None

    has_vlm_key = Path(".secrets/quicksilver_clutchbot.key").exists() or os.environ.get(
        "QUICKSILVER_API_KEY"
    )
    ocr_enabled = os.environ.get("QORESENCE_EASY_OCR", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not has_vlm_key and not ocr_enabled:
        pytest.skip("scoreboard reader not available: no VLM key and OCR disabled")

    frame = cv2.imread(str(path))
    assert frame is not None
    extractor = FootballScoreboardExtractor()
    ctx = VisualContext(game_category=GameCategory.FOOTBALL, game_state=GameState.GAMEPLAY)
    result = extractor.extract(frame, ctx)

    # If the frame was captured from a non-scoreboard screen (e.g. menu or
    # person), the score fields will be None. Skip in that case rather than
    # asserting on an accidental capture.
    if result.home_score is None and result.away_score is None:
        pytest.skip("eye_verify frame has no scoreboard fields")

    # left-of-center is away, right-of-center is home
    assert result.home_score == 7
    assert result.away_score == 0
    assert result.quarter == 1
    assert result.clock_seconds == 101  # 1:41
    assert result.down == 1
    assert result.yards_to_go == 10
    assert result.play_clock == 24
    assert result.down_distance_text == "1st & 10"


def test_extract_ignores_person_like_blank_frame():
    """A dark/blank frame passed as football should not get false scoreboard fields."""
    extractor = FootballScoreboardExtractor()
    ctx = VisualContext(game_category=GameCategory.FOOTBALL)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = extractor.extract(frame, ctx)
    # No scores/quarter should be invented from a blank image.
    assert result.quarter is None
    assert result.home_score is None
    assert result.away_score is None
