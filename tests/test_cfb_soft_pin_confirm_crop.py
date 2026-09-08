"""CFB soft pin + optical ticker markers for confirm crop (PR feat/cfb-soft-pin-confirm-crop)."""

from __future__ import annotations

import numpy as np

from qoresence.agents.situation_model import SituationModel
from qoresence.core.types import BaseEvent, EventType, SourceLobe
from qoresence.vision.cfb_optical_markers import (
    CFB_OPTICAL_RE,
    clear_football_confirm_hint,
    cfb_markers_in_text,
    frame_has_cfb_optical_markers,
)
from qoresence.vision.confirm_ticket import (
    ConfirmTicketBook,
    mint_confirm_ticket,
    ticket_is_licensed_lock,
)
from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee
from qoresence.vision.scorebug_crops import CFB_PRIMARY_SCOREBUG, MADDEN_PRIMARY_SCOREBUG


def _cfb_ticker_fixture(
    *,
    ticker_text: str = "EA SPORTS COLLEGE FOOTBALL 27",
    h: int = 720,
    w: int = 1280,
) -> np.ndarray:
    """Synthetic CFB HUD: scorebug band + bottom-left ticker product string."""
    import cv2

    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = (16, 20, 14)
    y1, y2 = int(h * 0.78), int(h * 0.93)
    frame[y1:y2, :] = (8, 40, 8)
    frame[int(h * 0.93) :, :] = (0, 0, 0)
    cv2.putText(
        frame,
        ticker_text,
        (int(w * 0.02), int(h * 0.98)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (220, 220, 220),
        2,
        cv2.LINE_AA,
    )
    frame[int(h * 0.93) :, :, 0] = 200
    return frame


def test_cfb_optical_regex_matches_college_football_27():
    assert CFB_OPTICAL_RE.search("EA SPORTS COLLEGE FOOTBALL 27")
    assert cfb_markers_in_text("COLLEGE FOOTBALL 27")
    assert cfb_markers_in_text("ncaa football")
    assert cfb_markers_in_text("cfb 27")
    assert not cfb_markers_in_text("MADDEN NFL 27")


def test_locked_cfb_title_stamps_mid_drive_confirm_context(monkeypatch):
    """HYST_LOCKED title stashes; mid-drive extract stamps empty ctx for CFB crop."""
    from qoresence.vision.cfb_optical_markers import (
        clear_football_confirm_hint,
        locked_optical_title,
        stamp_confirm_context,
    )
    from qoresence.vision.visual_context import GameCategory, GameState, VisualContext

    clear_football_confirm_hint()
    sit = SituationModel()
    sit.seed_profile("madden_27", pinned=True)
    sit.update(
        BaseEvent(
            session_id="s",
            clock_ns=1,
            source_lobe=SourceLobe.FUSION,
            type=EventType.TITLE_PRESENCE,
            payload={
                "claim": True,
                "profile_id": "ncaa_football_27",
                "display_name": "College Football 27",
                "hysteresis_state": "locked",
            },
        )
    )
    assert sit.state.game_profile == "cfb_27"
    locked_title, locked_profile = locked_optical_title()
    assert locked_title == "College Football 27"
    assert locked_profile == "cfb_27"

    frame = _cfb_ticker_fixture()
    monkeypatch.setattr(
        "qoresence.vision.cfb_optical_markers.read_ticker_strip_text",
        lambda _f: "EA SPORTS COLLEGE FOOTBALL 27",
    )
    ctx = VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        game_profile="madden_27",
        confidence=0.9,
    )
    stamp_confirm_context(ctx, frame)
    assert ctx.game_title == "College Football 27"
    assert ctx.game_profile == "cfb_27"


def test_fuse_evidence_scores_cfb_27_vlm_evidence():
    """VisionStack CFB_27 VLM evidence must contribute to fuse scores."""
    from qoresence.game_detection import DetectionEvidence, GameAutoDetector
    from qoresence.core import GameProfileId, RetinaEventBus

    det = GameAutoDetector(RetinaEventBus(session_id="s"), 0, vlm_client=None)
    now = 1_000_000_000
    det._evidence.append(
        DetectionEvidence(
            timestamp_ns=now,
            source="vlm",
            profile_id=GameProfileId.CFB_27,
            confidence=0.92,
            details={},
        )
    )
    result = det._fuse_evidence(now)
    assert result.profile_id == GameProfileId.CFB_27
    assert result.confidence > 0.0


def test_null_vlm_situation_blanks_scores_not_zero_zero():
    """Null VLM / unlicensed ticket → blank glass scores (□–□), never 0-0."""
    from qoresence.agents.situation_model import SituationModel

    sit = SituationModel()
    snap = sit.to_dict()
    assert snap["home_score"] is None
    assert snap["away_score"] is None
    assert snap["score_vlm_locked"] is False


def test_pinned_madden_locked_cfb_title_uses_cfb_primary_crop(monkeypatch):
    """Pinned madden + locked CFB title → situation cfb_27 + CFB_PRIMARY crop."""
    clear_football_confirm_hint()
    sit = SituationModel()
    sit.seed_profile("madden_27", pinned=True)
    sit.update(
        BaseEvent(
            session_id="s",
            clock_ns=1,
            source_lobe=SourceLobe.FUSION,
            type=EventType.TITLE_PRESENCE,
            payload={
                "claim": True,
                "profile_id": "ncaa_football_27",
                "display_name": "College Football 27",
                "hysteresis_state": "locked",
            },
        )
    )
    assert sit.state.game_profile == "cfb_27"

    frame = _cfb_ticker_fixture()
    monkeypatch.setattr(
        "qoresence.vision.cfb_optical_markers.read_ticker_strip_text",
        lambda _f: "EA SPORTS COLLEGE FOOTBALL 27",
    )
    crop = ScoreboardVlmReferee._crop(
        frame,
        game_state="gameplay",
        game_profile="madden_27",
        game_title=None,
    )
    assert crop is not None
    h, w = frame.shape[:2]
    x1, x2, y1, y2 = CFB_PRIMARY_SCOREBUG
    assert int(frame[int(h * y1) : int(h * y2), int(w * x1) : int(w * x2), 1].max()) >= 40


def test_madden_seed_null_title_ticker_college_football_uses_cfb_primary_crop(monkeypatch):
    """Seed madden_27 + null title + ticker COLLEGE FOOTBALL 27 → CFB_PRIMARY, not Madden."""
    clear_football_confirm_hint()
    frame = _cfb_ticker_fixture()
    monkeypatch.setattr(
        "qoresence.vision.cfb_optical_markers.read_ticker_strip_text",
        lambda _f: "EA SPORTS COLLEGE FOOTBALL 27",
    )
    assert frame_has_cfb_optical_markers(frame, game_profile="madden_27", game_title=None)

    h, w = frame.shape[:2]
    x1, x2, y1, y2 = CFB_PRIMARY_SCOREBUG
    cfb_band = frame[int(h * y1) : int(h * y2), int(w * x1) : int(w * x2)]
    assert int(cfb_band[:, :, 1].max()) >= 40

    crop = ScoreboardVlmReferee._crop(
        frame,
        game_state="gameplay",
        game_profile="madden_27",
        game_title=None,
    )
    assert crop is not None
    mx, my, mz = int(crop[:, :, 0].max()), int(crop[:, :, 1].max()), int(crop[:, :, 2].max())
    assert my >= 40, "CFB confirm crop must sample the green scorebug band, not Madden HUD"
    assert mx < 200 or my > mx, "Must not prefer the blue Madden ticker strip over CFB scorebug"


def test_madden_only_crop_without_cfb_markers_unchanged(monkeypatch):
    """Madden title/profile with no CFB ticker markers still uses Madden bands."""
    clear_football_confirm_hint()
    h, w = 720, 1280
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[int(h * 0.78) : int(h * 0.93), :, 1] = 255
    frame[int(h * 0.93) :, :, 0] = 255
    monkeypatch.setattr(
        "qoresence.vision.cfb_optical_markers.read_ticker_strip_text",
        lambda _f: "MADDEN NFL 27",
    )
    assert not frame_has_cfb_optical_markers(frame, game_profile="madden_27", game_title="Madden NFL 27")

    crop = ScoreboardVlmReferee._crop(
        frame,
        game_state="gameplay",
        game_profile="madden_27",
        game_title="Madden NFL 27",
    )
    assert crop is not None
    assert int(crop[:, :, 0].max()) == 255
    x1, x2, y1, y2 = MADDEN_PRIMARY_SCOREBUG
    assert y1 == 0.68


def test_soft_pin_situation_cfb_27_despite_madden_pin_locked_claim():
    """Locked CFB title claim yields over operator_pin=madden_27."""
    clear_football_confirm_hint()
    sit = SituationModel()
    sit.seed_profile("madden_27", pinned=True)
    ev = BaseEvent(
        session_id="s",
        clock_ns=1,
        source_lobe=SourceLobe.FUSION,
        type=EventType.TITLE_PRESENCE,
        payload={
            "claim": True,
            "profile_id": "ncaa_football_27",
            "display_name": "College Football 27",
            "hysteresis_state": "locked",
        },
    )
    sit.update(ev)
    assert sit.state.game_profile == "cfb_27"
    assert sit.state.title_hysteresis == "locked"
    assert sit.state.title_claim is True


def test_soft_pin_visual_context_cfb_profile_over_madden_pin():
    sit = SituationModel()
    sit.seed_profile("madden_27", pinned=True)
    ev = BaseEvent(
        session_id="s",
        clock_ns=1,
        source_lobe=SourceLobe.VISUAL,
        type=EventType.VISUAL_CONTEXT,
        payload={
            "game_profile": "cfb_27",
            "game_category": "football",
            "game_state": "gameplay",
            "confidence": 0.9,
        },
    )
    sit.update(ev)
    assert sit.state.game_profile == "cfb_27"


def test_madden_pin_still_holds_without_cfb_markers():
    sit = SituationModel()
    sit.seed_profile("madden_27", pinned=True)
    ev = BaseEvent(
        session_id="s",
        clock_ns=1,
        source_lobe=SourceLobe.FUSION,
        type=EventType.GAME_DETECTED,
        payload={"profile_id": "ncaa_football_27"},
    )
    sit.update(ev)
    assert sit.state.game_profile == "madden_27"


def test_null_vlm_parse_never_mints_zero_zero_ticket():
    """Null parse / empty crop_hash → no licensed 0-0 lock (fixtures only)."""
    book = ConfirmTicketBook()
    assert ScoreboardVlmReferee._parse_json("No scorebug visible on this frame.") is None
    zero = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=0,
        away_score=0,
        crop_hash="",
        book=book,
    )
    assert ticket_is_licensed_lock(zero) is False
    assert book.latest() is None or not ticket_is_licensed_lock(book.latest())
