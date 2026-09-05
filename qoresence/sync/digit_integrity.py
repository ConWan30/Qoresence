"""Digit void reasons — fail-closed. Blank beats last-good hold."""

from __future__ import annotations

CONFIRM_DIGIT_MAX_AGE_NS = 8_000_000_000

DigitVoidReason = str
FreshnessBand = str


def freshness_band(age_ns: int, max_age_ns: int = CONFIRM_DIGIT_MAX_AGE_NS) -> FreshnessBand:
    age = int(age_ns or 0)
    max_age = max(1, int(max_age_ns or CONFIRM_DIGIT_MAX_AGE_NS))
    if age > max_age:
        return "ident"
    if age > max_age * 0.8:
        return "red"
    if age > max_age * 0.5:
        return "amber"
    return "ok"


def digit_void_reason(
    *,
    confirm_ticket_id: str = "",
    score_vlm_locked: bool = False,
    path: str = "",
    ticket_crop_hash: str = "",
    live_crop_hash: str = "",
    same_seq: bool | None = None,
    ticket_clock_ns: int = 0,
    live_clock_ns: int = 0,
    vlm_abstain: bool = False,
) -> DigitVoidReason:
    if str(path or "").lower() == "fast":
        return "path_fast"
    if vlm_abstain:
        return "vlm_abstain"
    if not str(confirm_ticket_id or "").strip():
        return "no_ticket"
    if not score_vlm_locked:
        return "vlm_unlocked"
    ticket_crop = str(ticket_crop_hash or "").strip()
    live_crop = str(live_crop_hash or "").strip()
    if live_crop and ticket_crop and live_crop != ticket_crop:
        return "crop_mismatch"
    if same_seq is False:
        return "seq_skew"
    t_clock = int(ticket_clock_ns or 0)
    l_clock = int(live_clock_ns or 0)
    if t_clock > 0 and l_clock > 0 and l_clock - t_clock > CONFIRM_DIGIT_MAX_AGE_NS:
        return "ticket_stale"
    if not ticket_crop:
        return "ticket_stale"
    return "licensed"
