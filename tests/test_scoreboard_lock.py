"""Off-thread score lock: honest pairs lock; invented 3-2 does not."""

from __future__ import annotations

import threading

import numpy as np

from qoresence.vision.scoreboard_extractor import (
    FootballScoreboardExtractor,
    _ScoreStabilizer,
)
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


class _FakeVlm:
    def __init__(self, last: dict | None) -> None:
        self._last = last

    def schedule(self, *a, **k) -> None:
        return None

    def get_last(self) -> dict | None:
        return dict(self._last) if self._last else None


def _reset() -> None:
    FootballScoreboardExtractor._stabilizer = _ScoreStabilizer(window=6, need=2)


def _noise_frame() -> np.ndarray:
    rng = np.random.default_rng(7)
    frame = np.full((720, 1280, 3), 40, dtype=np.uint8)
    frame = np.clip(frame.astype(np.int16) + rng.integers(-10, 11, size=frame.shape), 0, 255)
    return frame.astype(np.uint8)


def _gameplay() -> VisualContext:
    return VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        game_profile="madden_27",
    )


def _grounded_board(home: int, away: int, **extra: object) -> dict:
    """Gemini read of THIS match's scorebug — teams on both sides."""
    board = {
        "home_score": home,
        "away_score": away,
        "home_left": False,
        "left_team": "KC",
        "right_team": "PHI",
        "quarter": 4,
        "clock_seconds": 185,
        "down": 2,
    }
    board.update(extra)
    return board


def _patch_empty_hud(monkeypatch) -> None:
    monkeypatch.delenv("QORESENCE_EASY_OCR", raising=False)
    monkeypatch.setattr(
        "qoresence.vision.local_hud_digits.read_score_pair",
        lambda *a, **k: None,
    )


def test_invented_3_2_without_local_board_does_not_lock(monkeypatch):
    """This morning: HUD empty all match, then a 3-2 lock. Refuse that."""
    _reset()
    monkeypatch.delenv("QORESENCE_EASY_OCR", raising=False)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm",
        lambda: _FakeVlm({"home_score": 3, "away_score": 2, "quarter": 4}),
    )
    monkeypatch.setattr(
        "qoresence.vision.local_hud_digits.read_score_pair",
        lambda *a, **k: None,
    )
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(_noise_frame(), _gameplay())
    assert ctx.score_vlm_locked is False
    assert ctx.home_score is None
    assert ctx.away_score is None
    assert not (ctx.confirm_ticket_id or "")


def test_grounded_vlm_locks_without_local_hud(monkeypatch):
    """Gameplay Gemini with both wordmarks must lock even when HUD blobs fail."""
    _reset()
    _patch_empty_hud(monkeypatch)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm",
        lambda: _FakeVlm(_grounded_board(24, 22)),
    )
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(_noise_frame(), _gameplay())
    assert (ctx.home_score, ctx.away_score) == (24, 22)
    assert ctx.score_vlm_locked is True
    assert ctx.confirm_ticket_id


def test_grounded_vlm_updates_held_pair_without_hud(monkeypatch):
    """Live scorebug changes must replace the held lock without waiting on HUD."""
    _reset()
    _patch_empty_hud(monkeypatch)
    vlm = _FakeVlm(_grounded_board(23, 22))
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm",
        lambda: vlm,
    )
    ext = FootballScoreboardExtractor()
    frame = _noise_frame()
    ctx = ext.extract(frame, _gameplay())
    assert (ctx.home_score, ctx.away_score) == (23, 22)
    assert ctx.score_vlm_locked is True
    vlm._last = _grounded_board(30, 22, clock_seconds=140)
    ctx = ext.extract(frame, _gameplay())
    assert (ctx.home_score, ctx.away_score) == (30, 22)
    assert ctx.score_vlm_locked is True
    assert ctx.confirm_ticket_id


def test_clock_grounded_vlm_locks_without_team_wordmarks(monkeypatch):
    """640x480 Madden: clock on the bug is enough; wordmarks may be null."""
    _reset()
    _patch_empty_hud(monkeypatch)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm",
        lambda: _FakeVlm(
            {
                "home_score": 17,
                "away_score": 14,
                "quarter": 3,
                "clock_seconds": 412,
                "left_team": None,
                "right_team": None,
            }
        ),
    )
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(_noise_frame(), _gameplay())
    assert (ctx.home_score, ctx.away_score) == (17, 14)
    assert ctx.score_vlm_locked is True
    assert ctx.confirm_ticket_id


def test_honest_18_13_from_hud_locks(monkeypatch):
    """HUD-only pair is not a seeing-path mint. Digits stay off the plane."""
    _reset()
    monkeypatch.delenv("QORESENCE_EASY_OCR", raising=False)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm",
        lambda: _FakeVlm(None),
    )
    monkeypatch.setattr(
        "qoresence.vision.local_hud_digits.read_score_pair",
        lambda *a, **k: (18, 13),
    )
    ext = FootballScoreboardExtractor()
    frame = _noise_frame()
    ctx = ext.extract(frame, _gameplay())
    ctx = ext.extract(frame, ctx)
    assert (ctx.home_score, ctx.away_score) == (None, None)
    assert ctx.score_vlm_locked is False
    assert not (ctx.confirm_ticket_id or "")


def test_menu_hud_pair_does_not_mint_lock(monkeypatch):
    _reset()
    monkeypatch.delenv("QORESENCE_EASY_OCR", raising=False)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm",
        lambda: _FakeVlm(None),
    )
    monkeypatch.setattr(
        "qoresence.vision.local_hud_digits.read_score_pair",
        lambda *a, **k: (3, 2),
    )
    ext = FootballScoreboardExtractor()
    ctx = VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.MENU,
        game_profile="madden_27",
    )
    frame = _noise_frame()
    ctx = ext.extract(frame, ctx)
    ctx = ext.extract(frame, ctx)
    assert ctx.score_vlm_locked is False
    assert not (ctx.confirm_ticket_id or "")


def test_menu_grounded_vlm_mints_football_hud(monkeypatch):
    """Play-call / pause still shows the match HUD. Grounded VLM may mint."""
    _reset()
    _patch_empty_hud(monkeypatch)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm",
        lambda: _FakeVlm(_grounded_board(10, 0)),
    )
    ctx = VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.MENU,
        game_profile="madden_27",
    )
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(_noise_frame(), ctx)
    assert ctx.score_vlm_locked is True
    assert ctx.confirm_ticket_id
    assert (ctx.home_score, ctx.away_score) == (10, 0)


def test_offer_extracts_off_caller_thread(monkeypatch):
    from qoresence.vision.scoreboard_lock import (
        offer_scoreboard_frame,
        reset_scoreboard_lock_worker,
        wait_scoreboard_lock,
    )

    reset_scoreboard_lock_worker()
    names: list[str] = []
    real_extract = FootballScoreboardExtractor.extract

    def _spy(self, frame, ctx, **kw):
        names.append(threading.current_thread().name)
        return real_extract(self, frame, ctx, **kw)

    monkeypatch.setattr(FootballScoreboardExtractor, "extract", _spy)
    caller = threading.current_thread().name
    offer_scoreboard_frame(_noise_frame(), _gameplay())
    assert caller not in names
    wait_scoreboard_lock(timeout_s=2.0)
    assert names
    assert all(n != caller for n in names)
    reset_scoreboard_lock_worker()


def test_extractor_init_does_not_start_paddle_when_ocr_off(monkeypatch):
    monkeypatch.delenv("QORESENCE_EASY_OCR", raising=False)
    called: list[int] = []

    def _boom(*_a, **_k):
        called.append(1)
        raise AssertionError("Paddle warmup must stay off unless QORESENCE_EASY_OCR=1")

    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        _boom,
    )
    FootballScoreboardExtractor._stabilizer = None
    FootballScoreboardExtractor()
    assert called == []
