"""Confirm ticket: DeepSeek lock licenses score speech."""

from __future__ import annotations

from qoresence.agents.society.policy import SocietyPolicy
from qoresence.agents.society.types import AgentPacket, AgentReceipt
from qoresence.vision.confirm_ticket import (
    ConfirmTicketBook,
    license_score_text,
    mint_confirm_ticket,
    mismatch_snapshot,
    why_strip,
)


def test_mint_is_deterministic_for_same_board():
    a = mint_confirm_ticket(
        session_id="sess-1",
        clock_ns=100,
        home_score=21,
        away_score=14,
        model="deepseek-v4-flash-vision-exp",
        source="deepseek",
        frame_seq=9,
        crop_hash="abc",
    )
    b = mint_confirm_ticket(
        session_id="sess-1",
        clock_ns=100,
        home_score=21,
        away_score=14,
        model="deepseek-v4-flash-vision-exp",
        source="deepseek",
        frame_seq=9,
        crop_hash="abc",
    )
    assert a.ticket_id == b.ticket_id
    assert len(a.ticket_id) == 16
    assert a.model == "deepseek-v4-flash-vision-exp"
    assert a.source == "deepseek"


def test_mint_defaults_to_qwen37_flash_on_quicksilver():
    t = mint_confirm_ticket(session_id="s", clock_ns=1, home_score=7, away_score=0)
    assert t.model == "qwen3.7-flash"
    assert t.model != "gemini-3.5-flash-lite"
    assert t.model != "deepseek-v4-flash"
    assert t.source == "quicksilver"


def test_different_scores_make_different_tickets():
    a = mint_confirm_ticket(session_id="s", clock_ns=1, home_score=21, away_score=14)
    b = mint_confirm_ticket(session_id="s", clock_ns=1, home_score=21, away_score=17)
    assert a.ticket_id != b.ticket_id


def test_book_keeps_latest_and_lookup():
    book = ConfirmTicketBook()
    t = mint_confirm_ticket(session_id="s", clock_ns=2, home_score=7, away_score=0)
    book.put(t)
    assert book.latest() is t
    assert book.get(t.ticket_id) is t


def test_license_strips_score_digits_without_ticket():
    raw = "Huge 21-14 in the red zone"
    out = license_score_text(raw, ticket=None, home_score=21, away_score=14)
    assert "21-14" not in out
    assert "board" in out


def test_license_keeps_matching_digits_with_ticket():
    t = mint_confirm_ticket(session_id="s", clock_ns=3, home_score=21, away_score=14)
    raw = "Score update: 21-14"
    out = license_score_text(raw, ticket=t, home_score=21, away_score=14)
    assert "21-14" in out


def test_society_requires_ticket_id_not_just_lock_flag():
    pol = SocietyPolicy(cooldown_s=0)
    pkt = AgentPacket(
        situation={"home_score": 14, "away_score": 13},
        score_vlm_locked=True,
    )
    rec = AgentReceipt(role="drive_coach", action="note", text="Board 14-13 holds")
    out = pol.finalize(rec, pkt)
    assert "14-13" not in out.text

    pkt.confirm_ticket_id = "deadbeefdeadbeef"
    pkt.situation["confirm_ticket_id"] = "deadbeefdeadbeef"
    rec2 = AgentReceipt(role="drive_coach", action="note", text="Board 14-13 holds")
    out2 = pol.finalize(rec2, pkt)
    assert "14-13" in out2.text
    assert out2.refs.get("ticket_id") == "deadbeefdeadbeef"


def test_why_strip_cites_ticket():
    t = mint_confirm_ticket(session_id="s", clock_ns=4, home_score=21, away_score=14, frame_seq=12)
    line = why_strip(t, last_fast={"kind": "fast_chat", "clock_ns": 1})
    assert t.ticket_id in line
    assert "21-14" in line
    assert "fast" in line.lower()


def test_mismatch_snapshot_pairs_fast_and_confirm():
    t = mint_confirm_ticket(session_id="s", clock_ns=50, home_score=3, away_score=0)
    snap = mismatch_snapshot(
        last_fast={"kind": "fast_clip", "clock_ns": 10, "reason": "coupling"},
        last_confirm=t,
    )
    assert snap["last_confirm"]["ticket_id"] == t.ticket_id
    assert snap["last_fast"]["kind"] == "fast_clip"
    assert snap["lag_ns"] == 40
