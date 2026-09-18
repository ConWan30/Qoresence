"""Digit void reasons — fail-closed. Blank beats last-good hold."""

from __future__ import annotations

from typing import Any

CONFIRM_DIGIT_MAX_AGE_NS = 8_000_000_000

DigitVoidReason = str
FreshnessBand = str

# One-team American-football scoring increments. Used as a mint-path veto
# (never a license). Safety = 2, FG = 3, TD = 6, TD+1 = 7, TD+2 = 8.
FOOTBALL_SCORE_DELTAS = frozenset({1, 2, 3, 6, 7, 8})


def _score_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def implausible_transition_reason(
    prior_home: Any,
    prior_away: Any,
    home: Any,
    away: Any,
) -> DigitVoidReason | None:
    """Why a proposed pair cannot follow a locked pair. None = no veto.

    Fail-closed on the seeing path: a drop, both sides moving, or a jump that
    is not a football increment (the 20-0 → 20-20 OCR echo) refuses the mint.
    Missing either pair is not a veto — cannot judge, so do not invent.
    """
    oh, oa = _score_int(prior_home), _score_int(prior_away)
    nh, na = _score_int(home), _score_int(away)
    if oh is None or oa is None or nh is None or na is None:
        return None
    dh = nh - oh
    da = na - oa
    if dh == 0 and da == 0:
        return None
    if dh < 0 or da < 0:
        return "implausible_transition"
    if dh != 0 and da != 0:
        return "implausible_transition"
    if (dh or da) not in FOOTBALL_SCORE_DELTAS:
        return "implausible_transition"
    return None


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
    implausible: bool = False,
) -> DigitVoidReason:
    if str(path or "").lower() == "fast":
        return "path_fast"
    if vlm_abstain:
        return "vlm_abstain"
    if implausible:
        return "implausible_transition"
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
