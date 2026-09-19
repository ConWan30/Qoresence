"""AgentGlass situation bag carries confirm_clock_ns + ticket_crop_hash after mint.

SEQGATE must not ticket_stale solely because ticket_crop was empty when the
ConfirmTicket is present, fresh, and published onto the live bag.
"""

from __future__ import annotations

import time

from qoresence.agents.agent_glass import AgentGlass
from qoresence.agents.situation_model import SituationModel
from qoresence.core.types import EventType, SourceLobe, make_event
from qoresence.sync.digit_integrity import digit_void_reason
from qoresence.sync.seqgate import gate_from_situation
from qoresence.vision.confirm_ticket import ConfirmTicketBook, mint_confirm_ticket
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


def _minted(*, clock_ns: int, crop_hash: str, book: ConfirmTicketBook | None = None):
    return mint_confirm_ticket(
        session_id="sess-crop-clock",
        clock_ns=clock_ns,
        home_score=21,
        away_score=14,
        crop_hash=crop_hash,
        source="quicksilver",
        book=book,
    )


def test_situation_bag_exports_clock_and_crop_after_visual_context():
    model = SituationModel()
    clock = time.monotonic_ns()
    crop = "scorebug-deadbeef"
    ctx = VisualContext(
        game_state=GameState.GAMEPLAY,
        game_category=GameCategory.FOOTBALL,
        home_score=21,
        away_score=14,
        score_vlm_locked=True,
        confirm_ticket_id="ticket-abc",
        confirm_clock_ns=clock,
        ticket_crop_hash=crop,
    )
    ev = make_event(
        "sess-crop-clock",
        clock,
        SourceLobe.VISUAL,
        EventType.VISUAL_CONTEXT,
        ctx.to_dict(),
    )
    model.update(ev)
    bag = model.to_dict()
    assert bag["confirm_ticket_id"] == "ticket-abc"
    assert bag["score_vlm_locked"] is True
    assert bag["confirm_clock_ns"] == clock
    assert bag["ticket_crop_hash"] == crop


def test_agent_glass_snapshot_publishes_ticket_crop_and_clock_from_book():
    book = ConfirmTicketBook()
    clock = time.monotonic_ns()
    crop = "scorebug-cafebabe"
    ticket = _minted(clock_ns=clock, crop_hash=crop, book=book)
    book.put(ticket)

    import qoresence.vision.confirm_ticket as ct

    prev = ct.get_ticket_book
    ct.get_ticket_book = lambda: book
    try:
        glass = AgentGlass(situation_provider=lambda: {"home_score": 21, "away_score": 14})
        snap = glass.snapshot()
    finally:
        ct.get_ticket_book = prev

    sit = snap["situation"]
    assert sit["confirm_ticket_id"] == ticket.ticket_id
    assert sit["confirm_clock_ns"] == clock
    assert sit["ticket_crop_hash"] == crop


def test_gate_not_ticket_stale_when_bag_has_fresh_crop_and_clock():
    clock = time.monotonic_ns()
    crop = "scorebug-fresh"
    sit = {
        "confirm_ticket_id": "t-1",
        "score_vlm_locked": True,
        "path": "confirm",
        "ticket_crop_hash": crop,
        "crop_hash": crop,
        "confirm_clock_ns": clock,
        "clock_ns": clock + 1_000_000,
        "home_score": 21,
        "away_score": 14,
        "same_seq": True,
    }
    gate = gate_from_situation(sit)
    assert gate["reason"] != "ticket_stale"
    assert gate["licensed"] is True
    assert gate["reason"] == "licensed"

    # Empty crop alone is ticket_stale — the bug publishing fields prevents.
    assert (
        digit_void_reason(
            confirm_ticket_id="t-1",
            score_vlm_locked=True,
            path="confirm",
            ticket_crop_hash="",
            live_crop_hash=crop,
            same_seq=True,
            ticket_clock_ns=clock,
            live_clock_ns=clock + 1_000_000,
        )
        == "ticket_stale"
    )
    assert (
        digit_void_reason(
            confirm_ticket_id="t-1",
            score_vlm_locked=True,
            path="confirm",
            ticket_crop_hash=crop,
            live_crop_hash=crop,
            same_seq=True,
            ticket_clock_ns=clock,
            live_clock_ns=clock + 1_000_000,
        )
        == "licensed"
    )
