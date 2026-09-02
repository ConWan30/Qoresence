"""Confirm crop must include the scorebug strip. Player CU must not mint.

Complementary HDMI LTR stamp: left_* from crop geometry, never homeLeft-swap.
#140 drafts the dedicated paint PR — this file owns the crop-band sit tests.
"""

from __future__ import annotations

import cv2
import numpy as np

from qoresence.agents.situation_model import SituationModel
from qoresence.core import BaseEvent, EventType, SourceLobe
from qoresence.vision.confirm_ticket import (
    ConfirmTicketBook,
    mint_confirm_ticket,
    mismatch_snapshot,
    overlay_hdmi_ltr,
)
from qoresence.vision.scoreboard_extractor import (
    confirm_crop_refuse,
    confirm_mint_refuse,
    garbage_lock_reason,
)
from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee
from qoresence.vision.scorebug_crops import (
    MADDEN_PRIMARY_SCOREBUG,
    MADDEN_SCOREBUG_CROPS,
    confirm_scorebug_bands,
    crop_contains,
    crop_misses_scorebug,
    looks_like_scorebug,
)
from qoresence.vision.visual_context import VisualContext, stamp_hdmi_ltr


def _player_cu_frame(h: int = 720, w: int = 1280) -> np.ndarray:
    """Image-1-like: 3D player huddle, NFL collar, no scorebug digits."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = (18, 36, 16)
    y1, y2 = int(h * 0.78), h
    x1, x2 = int(w * 0.22), int(w * 0.78)
    frame[y1:y2, x1:x2] = (236, 236, 236)
    frame[y1 : y1 + 48, x1 + 24 : x1 + 110] = (12, 170, 210)
    frame[y1 + 20 : y1 + 70, x1 + 40 : x1 + 90] = (20, 20, 20)
    return frame


def _scorebug_no40_det6(h: int = 720, w: int = 1280) -> np.ndarray:
    """Image-2-like: left NO 40 / right DET 6 on the bottom HUD above players."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = (16, 20, 14)
    y1, y2 = int(h * 0.70), int(h * 0.82)
    frame[y1:y2, :] = (8, 8, 8)
    cv2.putText(
        frame,
        "NO 40",
        (int(w * 0.06), int(h * 0.79)),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.8,
        (255, 255, 255),
        4,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        "DET 6",
        (int(w * 0.70), int(h * 0.79)),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.8,
        (255, 255, 255),
        4,
        cv2.LINE_AA,
    )
    frame[int(h * 0.86) :, int(w * 0.28) : int(w * 0.72)] = (230, 230, 230)
    return frame


def test_madden_confirm_bands_exclude_pause_include_hud_above_players():
    bands = confirm_scorebug_bands("madden_27")
    assert bands[0] == MADDEN_PRIMARY_SCOREBUG
    assert crop_contains(MADDEN_PRIMARY_SCOREBUG, x=0.50, y=0.72)
    for band in bands:
        y1 = float(band[2])
        y2 = float(band[3])
        # Mid-frame pause plates, not the top postgame FINISH GAME plate.
        mid_pause = y1 >= 0.10 and y1 <= 0.35 and y2 <= 0.60 and (y2 - y1) >= 0.25
        assert not mid_pause
    assert (0.30, 0.70, 0.18, 0.55) not in MADDEN_SCOREBUG_CROPS
    assert (0.18, 0.82, 0.12, 0.42) not in MADDEN_SCOREBUG_CROPS


def test_player_cu_crop_must_not_look_like_scorebug():
    crop = ScoreboardVlmReferee._crop(
        _player_cu_frame(), game_state="gameplay", game_profile="madden_27"
    )
    assert crop is not None
    assert crop_misses_scorebug(crop) == "player_cu_crop"
    assert looks_like_scorebug(crop) is False


def test_player_cu_must_not_mint_last_confirm():
    """Hallucinated NO/DET on a player CU must fail-closed. No lock."""
    crop = ScoreboardVlmReferee._crop(
        _player_cu_frame(), game_state="gameplay", game_profile="madden_27"
    )
    refuse = crop_misses_scorebug(crop)
    assert refuse == "player_cu_crop"

    class _Ref:
        def last_crop_refuse(self):
            return refuse

    assert confirm_crop_refuse(_Ref()) == "player_cu_crop"
    # Isolated book: 40-6 DET/NO is not garbage. The process-global book is
    # leftover from other tests in CI and would return identity_swap.
    book = ConfirmTicketBook()
    assert (
        garbage_lock_reason(
            home=40, away=6, home_team="DET", away_team="NO", book=book
        )
        is None
    )
    dirty = ConfirmTicketBook()
    prior = mint_confirm_ticket(
        session_id="sess-cu-prior",
        clock_ns=1,
        home_score=14,
        away_score=7,
        home_team="KC",
        away_team="PHI",
        book=dirty,
    )
    dirty.put(prior, home_team="KC", away_team="PHI")
    assert (
        garbage_lock_reason(
            home=40, away=6, home_team="DET", away_team="NO", book=dirty
        )
        == "identity_swap"
    )
    assert (
        confirm_mint_refuse(
            home=40,
            away=6,
            home_team="DET",
            away_team="NO",
            book=book,
            vlm_ref=_Ref(),
        )
        == "player_cu_crop"
    )


def test_scorebug_no40_det6_crop_includes_bug_not_just_players():
    frame = _scorebug_no40_det6()
    tight = ScoreboardVlmReferee._slice(frame, (0.00, 1.00, 0.82, 1.00))
    assert tight is not None
    assert crop_misses_scorebug(ScoreboardVlmReferee._prepare_crop(tight)) is not None

    crop = ScoreboardVlmReferee._crop(frame, game_state="gameplay", game_profile="madden_27")
    assert crop is not None
    assert looks_like_scorebug(crop) is True
    assert crop_misses_scorebug(crop) is None


def test_scorebug_no40_det6_yields_left_no_40_right_det_6():
    """Crop geometry: left wordmark+digits / right wordmark+digits. home/away unchanged."""
    ctx = VisualContext(
        game_category="football",
        game_profile="madden_27",
        home_score=40,
        away_score=6,
        home_left=False,
        home_team="DET",
        away_team="NO",
    )
    stamp_hdmi_ltr(
        ctx,
        parsed={
            "left_team": "NO",
            "right_team": "DET",
            "left_score": 40,
            "right_score": 6,
            "home_score": 40,
            "away_score": 6,
            "home_left": False,
        },
    )
    assert ctx.home_score == 40
    assert ctx.away_score == 6
    assert ctx.home_left is False
    assert ctx.left_team == "NO"
    assert ctx.right_team == "DET"
    assert ctx.left_score == 40
    assert ctx.right_score == 6


def test_home_left_false_21_6_paints_no_21_det_6_not_swapped():
    """Crop left NO 21 / right DET 6. home_left=false must not paint NO 6 DET 21."""
    ctx = VisualContext(
        game_category="football",
        game_profile="madden_27",
        home_score=21,
        away_score=6,
        home_left=False,
        home_team="DET",
        away_team="NO",
    )
    stamp_hdmi_ltr(
        ctx,
        parsed={
            "left_team": "NO",
            "right_team": "DET",
            "home_score": 21,
            "away_score": 6,
            "home_left": False,
        },
    )
    assert ctx.home_score == 21
    assert ctx.away_score == 6
    assert ctx.left_team == "NO"
    assert ctx.right_team == "DET"
    assert ctx.left_score == 21
    assert ctx.right_score == 6

    book = ConfirmTicketBook()
    ticket = mint_confirm_ticket(
        session_id="sess-crop-band",
        clock_ns=100,
        home_score=21,
        away_score=6,
        model="qwen3.7-flash",
        source="quicksilver",
        frame_seq=9,
        crop_hash="no21det6",
        book=book,
    )
    tid = ticket.ticket_id
    over = overlay_hdmi_ltr(
        ticket,
        left_team="NO",
        right_team="DET",
        left_score=21,
        right_score=6,
    )
    assert over.ticket_id == tid
    assert over.home_score == 21
    assert over.away_score == 6
    assert over.left_team == "NO"
    assert over.right_team == "DET"
    assert over.left_score == 21
    assert over.right_score == 6
    lc = mismatch_snapshot(last_fast=None, last_confirm=over)["last_confirm"]
    assert lc["ticket_id"] == tid
    assert lc["left_team"] == "NO"
    assert lc["right_team"] == "DET"
    assert lc["left_score"] == 21
    assert lc["right_score"] == 6
    assert lc["home_score"] == 21
    assert lc["away_score"] == 6

    sm = SituationModel()
    sm.update(
        BaseEvent(
            session_id="test",
            clock_ns=1,
            source_lobe=SourceLobe.VISUAL,
            type=EventType.VISUAL_CONTEXT,
            payload=ctx.to_dict(),
        )
    )
    d = sm.to_dict()
    assert d["home_score"] == 21
    assert d["away_score"] == 6
    assert d["left_team"] == "NO"
    assert d["right_team"] == "DET"
    assert d["left_score"] == 21
    assert d["right_score"] == 6
    assert d["home_left"] is False


def test_vlm_madden_never_returns_pause_plate_on_player_plus_hud():
    """Pause plate (center) must not win when a bottom HUD exists."""
    h, w = 720, 1280
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[int(h * 0.12) : int(h * 0.52), int(w * 0.22) : int(w * 0.78), 2] = 255
    y1, y2 = int(h * 0.70), int(h * 0.82)
    frame[y1:y2, :] = (8, 8, 8)
    cv2.putText(
        frame,
        "NO 21",
        (int(w * 0.06), int(h * 0.79)),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.8,
        (255, 255, 255),
        4,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        "DET 6",
        (int(w * 0.70), int(h * 0.79)),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.8,
        (255, 255, 255),
        4,
        cv2.LINE_AA,
    )
    crop = ScoreboardVlmReferee._crop(frame, game_state="menu", game_profile="madden_27")
    assert crop is not None
    red_only = (crop[:, :, 2] >= 200) & (crop[:, :, 0] < 40) & (crop[:, :, 1] < 40)
    assert int(red_only.sum()) == 0
    assert looks_like_scorebug(crop) is True
