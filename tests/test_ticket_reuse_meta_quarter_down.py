"""scale_tick HOLD must advance quarter/down from minted parse, not book.latest()."""

from __future__ import annotations

from qoresence.vision.confirm_ticket import (
    ConfirmTicketBook,
    mint_confirm_ticket,
    reuse_hold_refresh_ticket,
)


def test_mint_reuse_carries_new_quarter_down():
    book = ConfirmTicketBook()
    t1 = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=35,
        away_score=7,
        quarter=2,
        down=1,
        home_team="TEN",
        away_team="NYJ",
        book=book,
    )
    book.put(t1, home_team="TEN", away_team="NYJ")
    t2 = mint_confirm_ticket(
        session_id="s",
        clock_ns=2,
        home_score=35,
        away_score=7,
        quarter=3,
        down=2,
        home_team="TEN",
        away_team="NYJ",
        book=book,
    )
    assert t2.ticket_id == t1.ticket_id
    assert t2.quarter == 3
    assert t2.down == 2


def test_reuse_hold_refresh_keeps_minted_quarter_down():
    book = ConfirmTicketBook()
    stale = mint_confirm_ticket(
        session_id="s",
        clock_ns=1_000,
        home_score=35,
        away_score=7,
        quarter=2,
        down=1,
        frame_seq=100,
        crop_hash="crop-q2",
        home_team="TEN",
        away_team="NYJ",
        book=book,
    )
    book.put(stale, home_team="TEN", away_team="NYJ")
    minted = mint_confirm_ticket(
        session_id="s",
        clock_ns=2_000,
        home_score=35,
        away_score=7,
        quarter=3,
        down=2,
        frame_seq=200,
        crop_hash="crop-q3",
        home_team="TEN",
        away_team="NYJ",
        book=book,
    )
    assert minted.ticket_id == stale.ticket_id
    assert book.latest() is not None
    assert book.latest().quarter == 2
    assert book.latest().down == 1

    held = reuse_hold_refresh_ticket(
        minted,
        clock_ns=9_000_000_000,
        frame_seq=250,
        crop_hash="crop-q3-fresh",
    )
    assert held.ticket_id == minted.ticket_id
    assert held.quarter == 3
    assert held.down == 2
    assert held.clock_ns == 9_000_000_000
    assert held.frame_seq == 250
    assert held.crop_hash == "crop-q3-fresh"
    assert held.home_score == 35
    assert held.away_score == 7

    book.put(held, home_team="TEN", away_team="NYJ")
    live = book.latest()
    assert live is not None
    assert live.quarter == 3
    assert live.down == 2
