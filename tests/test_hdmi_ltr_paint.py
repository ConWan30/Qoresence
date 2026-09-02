"""HDMI left→right paint overlay. Does not remint ConfirmTicket. Bind never mints digits."""

from __future__ import annotations

from qoresence.agents.situation_model import SituationModel
from qoresence.core import BaseEvent, EventType, SourceLobe
from qoresence.profiles.team_identity import apply_identity_to_context
from qoresence.vision.confirm_ticket import (
    ConfirmTicketBook,
    mint_confirm_ticket,
    mismatch_snapshot,
    overlay_hdmi_ltr,
)
from qoresence.vision.visual_context import VisualContext, stamp_hdmi_ltr


def _mint_no21_det6(*, book: ConfirmTicketBook | None = None):
    return mint_confirm_ticket(
        session_id="sess-hdmi-ltr",
        clock_ns=100,
        home_score=21,
        away_score=6,
        model="qwen3.7-flash",
        source="quicksilver",
        frame_seq=9,
        crop_hash="no21det6",
        book=book if book is not None else ConfirmTicketBook(),
    )


def test_stamp_hdmi_ltr_no21_det6_copies_home_away_without_home_left_invert():
    """Madden HDMI crop: left NO 21 / right DET 6. home=21 away=6 home_left=false."""
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
    assert ctx.home_left is False
    assert ctx.left_team == "NO"
    assert ctx.right_team == "DET"
    assert ctx.left_score == 21
    assert ctx.right_score == 6


def test_overlay_does_not_remint_or_hash_ltr():
    t = _mint_no21_det6()
    tid = t.ticket_id
    assert t.home_score == 21
    assert t.away_score == 6
    over = overlay_hdmi_ltr(
        t,
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
    again = _mint_no21_det6()
    assert again.ticket_id == tid
    snap = mismatch_snapshot(last_fast=None, last_confirm=over)
    lc = snap["last_confirm"]
    assert lc["ticket_id"] == tid
    assert lc["home_score"] == 21
    assert lc["away_score"] == 6
    assert lc["left_team"] == "NO"
    assert lc["right_team"] == "DET"
    assert lc["left_score"] == 21
    assert lc["right_score"] == 6


def test_situation_to_dict_and_visual_context_round_trip_ltr():
    ctx = VisualContext.from_dict(
        {
            "game_state": "gameplay",
            "game_category": "football",
            "game_profile": "madden_27",
            "home_score": 21,
            "away_score": 6,
            "home_left": False,
            "home_team": "DET",
            "away_team": "NO",
            "left_team": "NO",
            "right_team": "DET",
            "left_score": 21,
            "right_score": 6,
            "score_vlm_locked": True,
            "confirm_ticket_id": "fixture-no21-det6",
        }
    )
    assert ctx.left_team == "NO"
    assert ctx.right_team == "DET"
    assert ctx.left_score == 21
    assert ctx.right_score == 6
    fb = ctx.to_dict()["football"]
    assert fb["home_score"] == 21
    assert fb["away_score"] == 6
    assert fb["left_team"] == "NO"
    assert fb["right_score"] == 6
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


def test_bind_scoreboard_sides_not_used_to_mint_madden_digits():
    """Bind remaps CFB identity; Madden apply_identity is a no-op. Overlay does not mint."""
    ctx = VisualContext(
        game_category="football",
        game_profile="madden_27",
        home_score=21,
        away_score=6,
        home_left=False,
    )
    apply_identity_to_context(
        ctx,
        {
            "game_profile": "madden_27",
            "left_team": "NO",
            "right_team": "DET",
            "home_score": 21,
            "away_score": 6,
            "home_left": False,
        },
    )
    assert ctx.home_score == 21
    assert ctx.away_score == 6
    t = _mint_no21_det6()
    over = overlay_hdmi_ltr(t, left_team="NO", right_team="DET", left_score=21, right_score=6)
    assert over.ticket_id == t.ticket_id
    assert over.home_score == 21
    assert over.away_score == 6
