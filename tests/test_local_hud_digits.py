"""Local HUD digit lock is fail-closed — never invents a score."""

from __future__ import annotations

import numpy as np

from qoresence.vision.local_hud_digits import read_score_pair
from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor
from qoresence.vision.visual_context import GameCategory, VisualContext


def _blank_madden() -> np.ndarray:
    # 720p dark frame — bottom HUD strip empty
    return np.full((720, 1280, 3), 18, dtype=np.uint8)


def test_empty_hud_does_not_invent_score():
    assert read_score_pair(_blank_madden(), "madden_27") is None
    assert read_score_pair(_blank_madden(), "ncaa_football_27") is None


def test_tiny_frame_is_none():
    assert read_score_pair(np.zeros((40, 80, 3), dtype=np.uint8), "madden_27") is None


def test_madden_pair_drops_center_yard_line():
    """Standard Madden bug: 21 left, yard 22 center, 7 right. Mid-split locked 7-22."""
    from qoresence.vision.local_hud_digits import pair_from_x_values

    assert pair_from_x_values([(0.10, 21), (0.55, 22), (0.88, 7)]) == (7, 21)
    assert pair_from_x_values([(0.12, 7), (0.58, 22)]) is None


def test_extractor_empty_hud_stays_unlocked(monkeypatch):
    FootballScoreboardExtractor._stabilizer = None
    monkeypatch.delenv("QORESENCE_EASY_OCR", raising=False)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm",
        lambda: type(
            "V", (), {"schedule": lambda *a, **k: None, "get_last": lambda *a, **k: None}
        )(),
    )
    ext = FootballScoreboardExtractor()
    ctx = VisualContext(game_category=GameCategory.FOOTBALL, game_profile="madden_27")
    out = ext.extract(_blank_madden(), ctx)
    assert out.home_score is None
    assert out.away_score is None
    assert out.score_vlm_locked is False
