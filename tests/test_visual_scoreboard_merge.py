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
        self.model = "qwen3.7-flash"
        self.base_url = ""

    def schedule(self, *a, **k):
        return None

    def get_last(self):
        return dict(self._last)

    def last_crop_refuse(self):
        return None


def _scorebug_frame() -> np.ndarray:
    """Confirm crop must contain wordmarks + digits. Gray noise is a player-CU refuse."""
    import cv2

    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:, :] = (16, 20, 14)
    y1, y2 = int(720 * 0.78), int(720 * 0.93)
    frame[y1:y2, :] = (8, 8, 8)
    cv2.putText(
        frame, "SMU 10", (int(1280 * 0.08), int(720 * 0.88)),
        cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 4, cv2.LINE_AA,
    )
    cv2.putText(
        frame, "LOU 14", (int(1280 * 0.62), int(720 * 0.88)),
        cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 4, cv2.LINE_AA,
    )
    return frame


def test_cloud_analyze_merges_gemini_board_and_mints_ticket(monkeypatch):
    FootballScoreboardExtractor._stabilizer = _ScoreStabilizer(window=6, need=2)
    from qoresence.vision.confirm_ticket import get_ticket_book
    from qoresence.vision.scoreboard_lock import reset_scoreboard_lock_worker

    get_ticket_book().clear()
    reset_scoreboard_lock_worker()
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
    monkeypatch.setattr(
        "qoresence.vision.local_hud_digits.read_score_pair",
        lambda *a, **k: (14, 10),
    )

    with tempfile.TemporaryDirectory() as td:
        bus = RetinaEventBus(session_id="t", jsonl_path=Path(td) / "e.jsonl", enable_ws=False)
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
        rt._analyze_frame(_scorebug_frame())
        from qoresence.vision.scoreboard_lock import (
            apply_scoreboard_lock,
            wait_scoreboard_lock,
        )

        wait_scoreboard_lock(timeout_s=2.0)
        if rt._last_context is not None:
            rt._last_context = apply_scoreboard_lock(rt._last_context)
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


def test_injected_vlm_on_noise_frame_does_not_mint(monkeypatch):
    """Gemini JSON on a gray frame is the 2026-09-01 player-CU lock. Fail-closed."""
    from qoresence.vision.confirm_ticket import get_ticket_book

    FootballScoreboardExtractor._stabilizer = _ScoreStabilizer(window=6, need=2)
    get_ticket_book().clear()
    vlm = _FakeVlm(
        {
            "home_score": 14,
            "away_score": 10,
            "quarter": 2,
            "left_team": "SMU",
            "right_team": "Louisville",
        }
    )
    monkeypatch.setattr("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm)
    monkeypatch.setattr(
        "qoresence.vision.local_hud_digits.read_score_pair",
        lambda *a, **k: (14, 10),
    )
    rng = np.random.default_rng(1)
    frame = np.full((720, 1280, 3), 80, dtype=np.uint8)
    frame = np.clip(frame.astype(np.int16) + rng.integers(-6, 7, size=frame.shape), 0, 255)
    ctx = VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        confidence=0.9,
        game_profile="ncaa_football_27",
    )
    result = FootballScoreboardExtractor().extract(frame.astype(np.uint8), ctx, allow_ocr=False)
    assert result.score_vlm_locked is False
    assert not (result.confirm_ticket_id or "")


def test_vlm_14_3_is_not_suspicious():
    """Field-goal 14-3 must lock; 3 is a real football score."""
    assert _ScoreStabilizer._looks_suspicious_pair((14, 3)) is False
    assert _ScoreStabilizer._looks_suspicious_pair((7, 3)) is False
    assert _ScoreStabilizer._looks_suspicious_pair((17, 2)) is True
    assert _ScoreStabilizer._looks_suspicious_pair((20, 0)) is False
