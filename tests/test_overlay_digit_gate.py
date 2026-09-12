"""Lens/Deck digit license — ConfirmTicket + VLM lock + ticket-fresh. Blank beats last-good."""

from __future__ import annotations

from pathlib import Path

DECK = Path(__file__).resolve().parents[1] / "qoresence" / "deck"


def test_overlay_digits_licensed_matches_ticket_fresh_clock_age():
    html = (DECK / "overlay.html").read_text(encoding="utf-8")
    assert "function digitsLicensed" in html
    assert "ticket_id" in html
    assert "score_vlm_locked" in html
    assert "crop_hash" in html
    # Same 8s confirm window as glass ticketFresh / CONFIRM_DIGIT_MAX_AGE_NS.
    compact = html.replace(" ", "")
    assert "8000000000" in compact or "8e9" in compact.lower() or "8_000_000_000" in html
    # Live clock must be FrameHub video.clock_ns, not Deck updated_ns.
    assert "video.clock_ns" in html
    assert "snap.updated_ns||" not in html.replace(" ", "")
    # Scorebug crop chain — hub full-frame video.crop_hash is not ticket crop.
    assert "s.live_crop_hash||s.crop_hash||s.frame_hash" in compact
    assert "video.crop_hash||s.crop_hash||s.frame_hash" not in compact
    assert "path" in html and "fast" in html
    assert "□–□" in html
    assert "SEQGATE" in html


def test_deck_html_does_not_license_on_scoreboard_locked_alone():
    html = (DECK / "deck.html").read_text(encoding="utf-8")
    # Last-good-adjacent: scoreboard_locked OR confirm_ticket_id without VLM lock.
    assert "scoreboard_locked||s.confirm_ticket_id" not in html.replace(" ", "")
    assert "score_vlm_locked" in html
    assert "confirm_ticket_id" in html


def test_overlay_is_not_operator_integrity_board():
    html = (DECK / "overlay.html").read_text(encoding="utf-8")
    assert "integrity-board" not in html
    assert "coupling-meter" not in html
    assert "LEASE OK" not in html


def test_mobile_html_does_not_license_on_title_claim_or_scoreboard_alone():
    html = (DECK / "mobile.html").read_text(encoding="utf-8")
    compact = html.replace(" ", "")
    assert "scoreboard_locked||s.title_claim" not in compact
    assert "score_vlm_locked||s.scoreboard_locked||s.title_claim" not in compact
    assert "score_vlm_locked" in html
