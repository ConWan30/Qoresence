"""Cloud visual path must merge Gemini scoreboard → lock + ticket."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from qoresence.core import RetinaEventBus, SessionAuthority, VisualConfig
from qoresence.lobes.visual import VisualRuntime
from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor, _ScoreStabilizer
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


class _FakeVlm:
    def __init__(self, last: dict):
        self._last = last

    def schedule(self, *a, **k):
        return None

    def get_last(self):
        return dict(self._last)


def _frame() -> np.ndarray:
    rng = np.random.default_rng(1)
    frame = np.full((720, 1280, 3), 80, dtype=np.uint8)
    frame = np.clip(frame.astype(np.int16) + rng.integers(-6, 7, size=frame.shape), 0, 255)
    return frame.astype(np.uint8)


def test_cloud_analyze_merges_gemini_board_and_mints_ticket(monkeypatch):
    FootballScoreboardExtractor._stabilizer = _ScoreStabilizer(window=6, need=2)
    vlm = _FakeVlm(
        {
            "home_score": 14,
            "away_score": 10,
            "quarter": 2,
            "home_left": False,
            "left_team": "SMU",
            "left_color": "blue",
            "left_logo": "mustang",
            "right_team": "Louisville",
            "right_color": "red",
            "right_logo": "cardinal",
        }
    )
    monkeypatch.setattr("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm)

    with tempfile.TemporaryDirectory() as td:
        bus = RetinaEventBus(
            session_id="t", jsonl_path=Path(td) / "e.jsonl", enable_ws=False
        )
        ident = SessionAuthority.mint(session_id="t")
        rt = VisualRuntime(
            VisualConfig(enabled=True, game_category="football", game_profile="ncaa_football_27"),
            bus,
            ident.session_head_ns,
        )
        classified = VisualContext(
            game_category=GameCategory.FOOTBALL,
            game_state=GameState.GAMEPLAY,
            confidence=0.9,
            game_profile="ncaa_football_27",
        )
        rt._client = Mock()
        rt._client.analyze_frame.return_value = classified
        rt._analyze_frame(_frame())
        rt.stop()
        bus.close()

    ctx = rt.get_last_context()
    assert ctx is not None
    assert ctx.score_vlm_locked is True
    assert (ctx.home_score, ctx.away_score) == (14, 10)
    assert ctx.confirm_ticket_id
    assert ctx.away_team == "SMU"
    assert ctx.home_team == "LOU"
    assert ctx.away_color == "blue"
    assert ctx.home_logo and "cardinal" in ctx.home_logo


def test_vlm_14_3_is_not_suspicious():
    """Field-goal 14-3 must lock; 3 is a real football score."""
    assert _ScoreStabilizer._looks_suspicious_pair((14, 3)) is False
    assert _ScoreStabilizer._looks_suspicious_pair((7, 3)) is False
    assert _ScoreStabilizer._looks_suspicious_pair((17, 2)) is True
    assert _ScoreStabilizer._looks_suspicious_pair((20, 0)) is False
