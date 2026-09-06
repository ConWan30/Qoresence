"""Digit void reasons — inverse of Scoreboard OCR last-good. Blank beats hold."""

from __future__ import annotations

from qoresence.sync.digit_integrity import (
    CONFIRM_DIGIT_MAX_AGE_NS,
    digit_void_reason,
    freshness_band,
)

LICENSED = {
    "confirm_ticket_id": "c-1",
    "score_vlm_locked": True,
    "path": "confirm",
    "ticket_crop_hash": "crop-a",
    "live_crop_hash": "crop-a",
    "same_seq": True,
    "ticket_clock_ns": 1_000,
    "live_clock_ns": 2_000,
}


def test_no_ticket_ignores_last_good_scores():
    assert digit_void_reason(**{**LICENSED, "confirm_ticket_id": ""}) == "no_ticket"


def test_unlocked_vlm():
    assert digit_void_reason(**{**LICENSED, "score_vlm_locked": False}) == "vlm_unlocked"


def test_path_fast_never_licenses():
    assert digit_void_reason(**{**LICENSED, "path": "fast"}) == "path_fast"


def test_stale_ticket():
    assert (
        digit_void_reason(
            **{
                **LICENSED,
                "ticket_clock_ns": 1,
                "live_clock_ns": 1 + CONFIRM_DIGIT_MAX_AGE_NS + 1,
            }
        )
        == "ticket_stale"
    )
    assert freshness_band(CONFIRM_DIGIT_MAX_AGE_NS + 1) == "ident"


def test_licensed_fresh():
    assert digit_void_reason(**LICENSED) == "licensed"
    assert freshness_band(0) == "ok"
    assert freshness_band(int(CONFIRM_DIGIT_MAX_AGE_NS * 0.7)) == "amber"
    assert freshness_band(int(CONFIRM_DIGIT_MAX_AGE_NS * 0.9)) == "red"
