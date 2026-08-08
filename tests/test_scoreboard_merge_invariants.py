"""Invariant tests for the scoreboard VLM ↔ OCR merge path.

Covers engineering invariants #4 and #5 from the Qoresence briefing:

- #4: Scoreboard VLM lock wins over conflicting digit-OCR when coherent.
- #5: Null VLM does not wipe a good score lock.

These exercise the *integration* merge path in
``FootballScoreboardExtractor.extract`` (VLM force-lock vs OCR consensus) and
the downstream ``SituationModel`` plausibility gate, not just isolated units.
"""

from __future__ import annotations

import numpy as np
import pytest

from qoresence.agents.situation_model import SituationModel
from qoresence.core import BaseEvent, EventType, SourceLobe
from qoresence.vision.scoreboard_extractor import (
    FootballScoreboardExtractor,
    _ScoreStabilizer,
)
from qoresence.vision.scoreboard_ocr_engine import OcrBox
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


# ── helpers ──────────────────────────────────────────────────────────────────


def _reset_stabilizer() -> None:
    """Reset the process-wide stabilizer so tests are independent."""
    FootballScoreboardExtractor._stabilizer = _ScoreStabilizer(window=6, need=2)


class _FakeOcrEngine:
    """Returns canned OcrBox tokens regardless of the crop."""

    name = "fake"

    def __init__(self, boxes: list[OcrBox]) -> None:
        self._boxes = boxes

    def is_ready(self) -> bool:
        return True

    def start_warmup(self) -> None:
        pass

    def read_boxes(self, bgr: np.ndarray) -> list[OcrBox]:
        return list(self._boxes)


class _FakeVlm:
    """Stand-in for ScoreboardVlmReferee with a fixed last result."""

    def __init__(self, last: dict | None) -> None:
        self._last = last

    def schedule(self, frame, *, force=False, reason="tick", game_state=None) -> None:
        pass

    def get_last(self) -> dict | None:
        return dict(self._last) if self._last else None


def _blank_frame() -> np.ndarray:
    return np.zeros((720, 1280, 3), dtype=np.uint8)


def _football_ctx() -> VisualContext:
    return VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
    )


def _ocr_boxes_20_20() -> list[OcrBox]:
    """OCR tokens that parse to 20-20 (the classic CFB digit-soup misread)."""
    return [
        OcrBox(text="HOME", x=0.20, y=0.45, conf=0.9, w=0.10, h=0.05),
        OcrBox(text="20", x=0.35, y=0.45, conf=0.95, w=0.06, h=0.08),
        OcrBox(text="20", x=0.65, y=0.45, conf=0.95, w=0.06, h=0.08),
        OcrBox(text="AWAY", x=0.80, y=0.45, conf=0.9, w=0.10, h=0.05),
    ]


def _ocr_boxes_20_0() -> list[OcrBox]:
    """OCR tokens that parse to 20-0 (the true CFB blowout)."""
    return [
        OcrBox(text="HOME", x=0.20, y=0.45, conf=0.9, w=0.10, h=0.05),
        OcrBox(text="20", x=0.35, y=0.45, conf=0.95, w=0.06, h=0.08),
        OcrBox(text="0", x=0.65, y=0.45, conf=0.93, w=0.04, h=0.08),
        OcrBox(text="AWAY", x=0.80, y=0.45, conf=0.9, w=0.10, h=0.05),
    ]


def _visual_context_event(payload: dict) -> BaseEvent:
    return BaseEvent(
        session_id="test",
        clock_ns=0,
        source_lobe=SourceLobe.VISUAL,
        type=EventType.VISUAL_CONTEXT,
        payload=payload,
    )


# ── invariant #4: VLM lock wins over conflicting OCR ─────────────────────────


def test_vlm_20_0_overrides_ocr_20_20(monkeypatch):
    """VLM reads 20-0 while OCR misreads 20-20; VLM must win (invariant #4)."""
    _reset_stabilizer()
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine(_ocr_boxes_20_20()),
    )
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm",
        lambda: _FakeVlm({"home_score": 20, "away_score": 0, "quarter": 3}),
    )
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(_blank_frame(), _football_ctx())
    assert ctx.home_score == 20
    assert ctx.away_score == 0  # VLM 0, not OCR 20
    assert ctx.score_vlm_locked is True


def test_vlm_lock_persists_when_ocr_keeps_misreading(monkeypatch):
    """After VLM locks 20-0, continued OCR 20-20 frames must not flip back."""
    _reset_stabilizer()
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine(_ocr_boxes_20_20()),
    )
    vlm = _FakeVlm({"home_score": 20, "away_score": 0, "quarter": 3})
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm
    )
    ext = FootballScoreboardExtractor()
    # VLM locks 20-0
    ctx = ext.extract(_blank_frame(), _football_ctx())
    assert (ctx.home_score, ctx.away_score) == (20, 0)
    # VLM goes stale (same last result); OCR still says 20-20 — must hold 20-0
    for _ in range(5):
        ctx = ext.extract(_blank_frame(), _football_ctx())
        assert (ctx.home_score, ctx.away_score) == (20, 0)


# ── invariant #5: null VLM does not wipe a good lock ──────────────────────────


def test_null_vlm_holds_prior_lock(monkeypatch):
    """VLM locks 20-0, then VLM returns null; stabilizer must hold 20-0."""
    _reset_stabilizer()
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine(_ocr_boxes_20_0()),
    )
    vlm = _FakeVlm({"home_score": 20, "away_score": 0, "quarter": 3})
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm
    )
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(_blank_frame(), _football_ctx())
    assert (ctx.home_score, ctx.away_score) == (20, 0)

    # VLM disappears (transition / blur / no key) — get_last returns None
    vlm = _FakeVlm(None)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm
    )
    # OCR also goes flaky (reads nothing useful)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine([]),
    )
    ctx = ext.extract(_blank_frame(), _football_ctx())
    assert (ctx.home_score, ctx.away_score) == (20, 0)  # lock held
    assert ctx.score_vlm_locked is False


def test_partial_vlm_does_not_wipe_lock(monkeypatch):
    """VLM returns only home (away=None); must not wipe a locked away score."""
    _reset_stabilizer()
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine(_ocr_boxes_20_0()),
    )
    vlm = _FakeVlm({"home_score": 20, "away_score": 0, "quarter": 3})
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm
    )
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(_blank_frame(), _football_ctx())
    assert (ctx.home_score, ctx.away_score) == (20, 0)

    # VLM partial: away is None → vlm_has_board False → scores not merged
    vlm = _FakeVlm({"home_score": 20, "away_score": None, "quarter": 3})
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm
    )
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine([]),
    )
    ctx = ext.extract(_blank_frame(), _football_ctx())
    assert (ctx.home_score, ctx.away_score) == (20, 0)  # lock held


# ── SituationModel downstream gate ────────────────────────────────────────────


def test_situation_model_accepts_vlm_correction():
    """VLM corrects 20-20 → 20-0; SituationModel must accept (invariant #4)."""
    sm = SituationModel()
    # Bad OCR lock: 20-20 accepted on first sight (prev=None)
    sm.update(
        _visual_context_event(
            {
                "game_category": "football",
                "game_state": "gameplay",
                "home_score": 20,
                "away_score": 20,
            }
        )
    )
    assert (sm.state.home_score, sm.state.away_score) == (20, 20)

    # VLM corrects to 20-0 with score_vlm_locked flag
    sm.update(
        _visual_context_event(
            {
                "game_category": "football",
                "game_state": "gameplay",
                "home_score": 20,
                "away_score": 0,
                "score_vlm_locked": True,
            }
        )
    )
    assert (sm.state.home_score, sm.state.away_score) == (20, 0)


def test_situation_model_still_rejects_ocr_drop_without_vlm():
    """Without VLM flag, a flaky OCR drop 17-17 → 17-2 must still be rejected."""
    sm = SituationModel()
    sm.update(
        _visual_context_event(
            {
                "game_category": "football",
                "game_state": "gameplay",
                "home_score": 17,
                "away_score": 17,
            }
        )
    )
    assert (sm.state.home_score, sm.state.away_score) == (17, 17)

    # Flaky OCR: away drops 17 → 2 (no VLM flag) — must be rejected
    sm.update(
        _visual_context_event(
            {
                "game_category": "football",
                "game_state": "gameplay",
                "home_score": 17,
                "away_score": 2,
            }
        )
    )
    assert sm.state.away_score == 17  # held, not wiped to 2


# ── to_dict / from_dict round-trip (production bus path) ──────────────────────


def test_score_vlm_locked_round_trips_through_dict():
    """The flag must survive to_dict → from_dict (bus serialization path)."""
    ctx = VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        home_score=20,
        away_score=0,
    )
    ctx.score_vlm_locked = True
    d = ctx.to_dict()
    assert d["score_vlm_locked"] is True
    rt = VisualContext.from_dict(d)
    assert rt.score_vlm_locked is True
    assert (rt.home_score, rt.away_score) == (20, 0)


def test_score_vlm_locked_defaults_false_in_round_trip():
    """Without the flag set, round-trip must default to False (OCR path)."""
    ctx = VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        home_score=17,
        away_score=17,
    )
    rt = VisualContext.from_dict(ctx.to_dict())
    assert rt.score_vlm_locked is False


# ── VLM-only path (no OCR — the default production config) ────────────────────


def test_vlm_only_merge_without_ocr(monkeypatch):
    """When QORESENCE_EASY_OCR is off (default), VLM scores still merge.

    This is the production bug: the extractor was never called when OCR was
    off, so VLM results were scheduled but never merged into the context.
    Now extract() always runs; only heavy OCR tokens are gated.
    """
    _reset_stabilizer()
    monkeypatch.delenv("QORESENCE_EASY_OCR", raising=False)
    # OCR engine would return tokens if called, but it must NOT be called
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine(_ocr_boxes_20_0()),
    )
    vlm = _FakeVlm({"home_score": 20, "away_score": 0, "quarter": 3})
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm
    )
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(_blank_frame(), _football_ctx())
    # VLM must merge even though OCR is off
    assert ctx.home_score == 20
    assert ctx.away_score == 0
    assert ctx.score_vlm_locked is True
