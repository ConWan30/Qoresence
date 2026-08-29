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
    """Synthetic frame with non-zero variance but no real scoreboard.

    The extractor's blank-frame guard rejects all-black images (std≈0).
    These tests need a frame that bypasses the guard so the VLM/OCR merge
    path can be exercised in isolation. A little noise + a gray field does
    the job without containing any OCR text.
    """
    rng = np.random.default_rng(42)
    frame = np.full((720, 1280, 3), 128, dtype=np.uint8)
    frame = frame.astype(np.int16) + rng.integers(-8, 9, size=frame.shape)
    frame = np.clip(frame, 0, 255).astype(np.uint8)
    return frame


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
    monkeypatch.setenv("QORESENCE_EASY_OCR", "1")
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
    assert getattr(ctx, "confirm_ticket_id", "")  # fail-closed mint


def test_vlm_lock_persists_when_ocr_keeps_misreading(monkeypatch):
    """After VLM locks 20-0, continued OCR 20-20 frames must not flip back."""
    _reset_stabilizer()
    monkeypatch.setenv("QORESENCE_EASY_OCR", "1")
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine(_ocr_boxes_20_20()),
    )
    vlm = _FakeVlm({"home_score": 20, "away_score": 0, "quarter": 3})
    monkeypatch.setattr("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm)
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
    monkeypatch.setenv("QORESENCE_EASY_OCR", "1")
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine(_ocr_boxes_20_0()),
    )
    vlm = _FakeVlm({"home_score": 20, "away_score": 0, "quarter": 3})
    monkeypatch.setattr("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm)
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(_blank_frame(), _football_ctx())
    assert (ctx.home_score, ctx.away_score) == (20, 0)

    # VLM disappears (transition / blur / no key) — get_last returns None
    vlm = _FakeVlm(None)
    monkeypatch.setattr("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm)
    # OCR also goes flaky (reads nothing useful)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine([]),
    )
    ctx = ext.extract(_blank_frame(), _football_ctx())
    assert (ctx.home_score, ctx.away_score) == (None, None)  # no seeing-path remint
    assert ctx.score_vlm_locked is False


def test_partial_vlm_does_not_wipe_lock(monkeypatch):
    """VLM returns only home (away=None); must not wipe a locked away score."""
    _reset_stabilizer()
    monkeypatch.setenv("QORESENCE_EASY_OCR", "1")
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine(_ocr_boxes_20_0()),
    )
    vlm = _FakeVlm({"home_score": 20, "away_score": 0, "quarter": 3})
    monkeypatch.setattr("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm)
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(_blank_frame(), _football_ctx())
    assert (ctx.home_score, ctx.away_score) == (20, 0)

    # VLM partial: away is None → vlm_has_board False → scores not merged
    vlm = _FakeVlm({"home_score": 20, "away_score": None, "quarter": 3})
    monkeypatch.setattr("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine([]),
    )
    ctx = ext.extract(_blank_frame(), _football_ctx())
    assert (ctx.home_score, ctx.away_score) == (None, None)  # no seeing-path remint
    assert ctx.score_vlm_locked is False


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
                "confirm_ticket_id": "cafecafecafecafe",
            }
        )
    )
    assert (sm.state.home_score, sm.state.away_score) == (20, 0)
    assert sm.state.score_vlm_locked is True
    assert sm.state.confirm_ticket_id == "cafecafecafecafe"
    snap = sm.to_dict()
    assert snap["score_vlm_locked"] is True
    assert snap["scoreboard_locked"] is True
    assert snap["confirm_ticket_id"] == "cafecafecafecafe"


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
        home_left=True,
    )
    ctx.score_vlm_locked = True
    d = ctx.to_dict()
    assert d["score_vlm_locked"] is True
    assert d["football"]["home_left"] is True
    rt = VisualContext.from_dict(d)
    assert rt.score_vlm_locked is True
    assert rt.home_left is True
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
    """Ungrounded VLM (scores + quarter only) must not invent a lock.

    Extract still runs when EasyOCR is off so a later local pair can merge.
    A lone Gemini pair on an empty HUD is how 3-2 locked after this morning's match.
    Grounded gameplay reads (wordmarks or clock) lock in test_scoreboard_lock.
    """
    _reset_stabilizer()
    monkeypatch.delenv("QORESENCE_EASY_OCR", raising=False)
    # OCR engine would return tokens if called, but it must NOT be called
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine(_ocr_boxes_20_0()),
    )
    vlm = _FakeVlm({"home_score": 20, "away_score": 0, "quarter": 3})
    monkeypatch.setattr("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm)
    ext = FootballScoreboardExtractor()
    ctx = ext.extract(_blank_frame(), _football_ctx())
    # VLM-only on an empty HUD invented 3-2 this morning. No local board → no lock.
    assert ctx.score_vlm_locked is False
    assert ctx.home_score is None
    assert ctx.away_score is None


# ── Orientation: home team on the left ────────────────────────────────────────


def test_ocr_home_left_override(monkeypatch):
    """If ctx.home_left is True, local OCR treats the left score as home."""
    _reset_stabilizer()
    monkeypatch.setenv("QORESENCE_EASY_OCR", "1")
    # HOME label on the left, score 20; AWAY label on the right, score 0.
    boxes = [
        OcrBox(text="HOME", x=0.20, y=0.45, conf=0.9, w=0.10, h=0.05),
        OcrBox(text="20", x=0.35, y=0.45, conf=0.95, w=0.06, h=0.08),
        OcrBox(text="0", x=0.65, y=0.45, conf=0.93, w=0.04, h=0.08),
        OcrBox(text="AWAY", x=0.80, y=0.45, conf=0.9, w=0.10, h=0.05),
    ]
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine(boxes),
    )
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: _FakeVlm(None)
    )
    ext = FootballScoreboardExtractor()
    ctx = VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        home_left=True,
    )
    # OCR path needs consensus; run twice to satisfy the stabilizer need=2.
    for _ in range(2):
        out = ext.extract(_blank_frame(), ctx)
    assert out.home_score == 20
    assert out.away_score == 0
    assert out.home_left is True


def test_ready_paddle_does_not_run_on_live_tick(monkeypatch):
    """Paddle on the visual/streamer tick freezes HDMI (age_s climbs, rebind loop)."""
    _reset_stabilizer()
    monkeypatch.delenv("QORESENCE_EASY_OCR", raising=False)
    calls = {"n": 0}

    class _Spy(_FakeOcrEngine):
        def read_boxes(self, bgr):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            return super().read_boxes(bgr)

    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _Spy(_ocr_boxes_20_0()),
    )
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: _FakeVlm(None)
    )
    ext = FootballScoreboardExtractor()
    ext.extract(_blank_frame(), _football_ctx())
    assert calls["n"] == 0


def test_ready_paddle_reads_madden_mnp_when_ocr_opted_in(monkeypatch):
    """NO 21 / CLE 7 — heavy OCR only when explicitly opted in."""
    _reset_stabilizer()
    monkeypatch.setenv("QORESENCE_EASY_OCR", "1")
    boxes = [
        OcrBox(text="NO", x=0.24, y=0.50, conf=0.9, w=0.06, h=0.40),
        OcrBox(text="21", x=0.33, y=0.50, conf=0.95, w=0.06, h=0.50),
        OcrBox(text="7", x=0.44, y=0.50, conf=0.95, w=0.04, h=0.50),
        OcrBox(text="CLE", x=0.52, y=0.50, conf=0.9, w=0.08, h=0.40),
        OcrBox(text="2ND", x=0.68, y=0.50, conf=0.9, w=0.06, h=0.40),
        OcrBox(text="37", x=0.92, y=0.50, conf=0.9, w=0.06, h=0.40),
    ]
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_ocr_engine.get_scoreboard_engine",
        lambda: _FakeOcrEngine(boxes),
    )
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: _FakeVlm(None)
    )
    ext = FootballScoreboardExtractor()
    ctx = VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        game_profile="madden_27",
    )
    out = None
    for _ in range(2):
        out = ext.extract(_blank_frame(), ctx)
    assert out is not None
    assert out.away_score == 21
    assert out.home_score == 7


# ── fail-closed: lock requires ConfirmTicket ──────────────────────────────────


def test_situation_model_refuses_lock_without_confirm_ticket():
    """score_vlm_locked without ticket_id must not license digits."""
    sm = SituationModel()
    sm.update(
        _visual_context_event(
            {
                "game_category": "football",
                "game_state": "gameplay",
                "home_score": 21,
                "away_score": 14,
                "score_vlm_locked": True,
                "confirm_ticket_id": "",
            }
        )
    )
    assert sm.state.score_vlm_locked is False
    assert not (sm.state.confirm_ticket_id or "")
    snap = sm.to_dict()
    assert snap.get("score_vlm_locked") is False


def test_situation_model_holds_locked_sides_when_home_left_flickers():
    """Same clubs swapped (VLM home_left flicker) must not invert the lock."""
    sm = SituationModel()
    sm.update(
        _visual_context_event(
            {
                "game_category": "football",
                "game_profile": "madden_27",
                "game_state": "gameplay",
                "home_score": 14,
                "away_score": 7,
                "home_team": "KC",
                "away_team": "PHI",
                "home_left": False,
                "score_vlm_locked": True,
                "confirm_ticket_id": "cafecafecafecafe",
            }
        )
    )
    assert (sm.state.home_team, sm.state.away_team) == ("KC", "PHI")
    assert sm.state.home_left is False

    sm.update(
        _visual_context_event(
            {
                "game_category": "football",
                "game_profile": "madden_27",
                "game_state": "gameplay",
                "home_score": 14,
                "away_score": 7,
                "home_team": "PHI",
                "away_team": "KC",
                "home_left": True,
                "score_vlm_locked": True,
                "confirm_ticket_id": "cafecafecafecafe",
            }
        )
    )
    assert (sm.state.home_team, sm.state.away_team) == ("KC", "PHI")
    assert sm.state.home_left is False
    assert (sm.state.home_score, sm.state.away_score) == (14, 7)
    assert sm.to_dict()["home_left"] is False


def test_deck_html_fmt_gates_unlocked_digits():
    """Legacy Rail fmt() must omit score pair unless locked."""
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "qoresence" / "deck" / "deck.html").read_text(
        encoding="utf-8"
    )
    assert "score_vlm_locked||s.scoreboard_locked||s.confirm_ticket_id" in html
    assert "locked&&s.home_score!=null" in html.replace(" ", "")


def test_identity_hysteresis_adopt_on_new_licensed_lock():
    """New licensed lock with incompatible identity adopts incoming identity.
    
    Regression test for identity hysteresis: when a licensed score arrives with
    a new confirm_ticket_id and incompatible team identity, the SituationModel
    must adopt the new identity instead of retaining the old one.
    
    Scenario: MEM/COLO 21-17 locked → incoming IND/DET 0-0 Q1 with new ticket
    Expected: situation wordmarks become IND/DET, not leftover MEM/COLO.
    """
    sm = SituationModel()
    
    # First: lock MEM/COLO with 21-17
    sm.update(
        _visual_context_event(
            {
                "game_category": "football",
                "game_state": "gameplay",
                "home_score": 21,
                "away_score": 17,
                "home_team": "MEM",
                "away_team": "COLO",
                "home_team_name": "Memphis",
                "away_team_name": "Colorado",
                "score_vlm_locked": True,
                "confirm_ticket_id": "ticket-mem-colo",
            }
        )
    )
    assert sm.state.home_team == "MEM"
    assert sm.state.away_team == "COLO"
    assert sm.state.home_team_name == "Memphis"
    assert sm.state.away_team_name == "Colorado"
    assert (sm.state.home_score, sm.state.away_score) == (21, 17)
    assert sm.state.score_vlm_locked is True
    assert sm.state.confirm_ticket_id == "ticket-mem-colo"
    
    # Second: new licensed lock IND/DET 0-0 Q1 with new ticket (incompatible identity)
    sm.update(
        _visual_context_event(
            {
                "game_category": "football",
                "game_state": "gameplay",
                "quarter": 1,
                "home_score": 0,
                "away_score": 0,
                "home_team": "IND",
                "away_team": "DET",
                "home_team_name": "Colts",
                "away_team_name": "Lions",
                "score_vlm_locked": True,
                "confirm_ticket_id": "ticket-ind-det",
            }
        )
    )
    
    # Assert: identity should be updated to IND/DET, not stuck on MEM/COLO
    assert sm.state.home_team == "IND", "home_team should update to IND"
    assert sm.state.away_team == "DET", "away_team should update to DET"
    assert sm.state.home_team_name == "Colts", "home_team_name should update to Colts"
    assert sm.state.away_team_name == "Lions", "away_team_name should update to Lions"
    assert (sm.state.home_score, sm.state.away_score) == (0, 0)
    assert sm.state.quarter == 1
    assert sm.state.score_vlm_locked is True
    assert sm.state.confirm_ticket_id == "ticket-ind-det"
