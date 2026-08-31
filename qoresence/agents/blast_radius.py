"""Blast-radius lanes for the learning edge.

Policy is data, not a confidence float. Irreversible actions stay closed
even when climax is high and even when a seeing-path ticket is present.
High climax without a ticket still cannot publish, wrap qortroller-truth,
or serialize score digits.
"""

from __future__ import annotations

from typing import Any

from qoresence.vision.confirm_ticket import ConfirmTicket, license_score_text
from qoresence.vision.title_presence_wrap import dest_denied

# Irreversible: closed even if climax is high.
IRREVERSIBLE = frozenset(
    {
        "publish",
        "mid_drive_publish",
        "wrap_qortroller_truth",
        "serialize_digits",
        "twitch_post",
        "second_capture",
        "mint_digits",
    }
)

REVERSIBLE_CONTAINED = frozenset(
    {
        "crop_band",
        "hysteresis",
        "rank_weight",
        "try_open",
        "schedule_skip",
        "freeze_weight",
        "correction_drop",
    }
)

REVERSIBLE_WIDE = frozenset(
    {
        "profile_swap",
        "rank_reweight_all",
    }
)


def classify_blast(action: str) -> str:
    a = str(action or "").strip()
    if a in IRREVERSIBLE:
        return "irreversible"
    if a in REVERSIBLE_CONTAINED:
        return "reversible_contained"
    if a in REVERSIBLE_WIDE:
        return "reversible_wide"
    return "irreversible"


def lane_allows(
    action: str,
    *,
    climax: float = 0.0,
    source_ticket_id: str = "",
    gate_green: bool = False,
) -> bool:
    """Gate on blast radius, not model confidence. Climax is ignored for closed lanes."""
    _ = climax  # observation only — never a gate
    kind = classify_blast(action)
    if kind == "irreversible":
        return False
    if kind == "reversible_wide" and not gate_green:
        return False
    if kind == "reversible_contained":
        return True
    return False


def cannot_serialize_digits(*, ticket: ConfirmTicket | None, text: str) -> str:
    """Fail-closed digit strip. No ticket → no pair."""
    return license_score_text(text, ticket=ticket)


def cannot_wrap_truth(dest: str = "qortroller-truth") -> bool:
    return dest_denied(dest)


def closed_lane_snapshot(
    *,
    climax: float,
    source_ticket_id: str = "",
    proposed_text: str = "score 21-14",
) -> dict[str, Any]:
    ticket_id = str(source_ticket_id or "").strip()
    return {
        "publish": lane_allows("publish", climax=climax, source_ticket_id=ticket_id),
        "wrap_qortroller_truth": lane_allows(
            "wrap_qortroller_truth", climax=climax, source_ticket_id=ticket_id
        )
        and not cannot_wrap_truth("qortroller-truth"),
        "serialize_digits": lane_allows(
            "serialize_digits", climax=climax, source_ticket_id=ticket_id
        ),
        "stripped": cannot_serialize_digits(ticket=None, text=proposed_text),
        "dest_denied": cannot_wrap_truth("qortroller-truth"),
    }
