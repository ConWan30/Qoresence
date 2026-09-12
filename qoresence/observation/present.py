"""Glass view of a lifecycle record. Does not change the journaled state."""

from __future__ import annotations

from copy import deepcopy

GLASS_STATE = {
    "candidate": "candidate",
    "tracking": "tracking",
    "provisional": "awaiting",
    "partial": "partial",
    "unresolved": "unresolved",
    "confirmed": "scoreboard_qualified",
}


def glass_state(state: str | None) -> str:
    """Overlay word. Journal may say confirmed; glass never says the play is certified."""
    return GLASS_STATE.get(str(state or ""), "unresolved")


def present_record(record: dict | None) -> dict | None:
    if not isinstance(record, dict):
        return record
    out = deepcopy(record)
    out["glass_state"] = glass_state(record.get("state"))
    out["glass_claim"] = (
        "scoreboard observed; play outcome unassigned"
        if record.get("claims")
        else "awaiting evidence; play outcome unassigned"
    )
    return out


def present_snapshot(snapshot: dict | None) -> dict:
    raw = dict(snapshot or {})
    raw["records"] = [present_record(r) for r in raw.get("records") or []]
    raw["revisions"] = [present_record(r) for r in raw.get("revisions") or []]
    return raw
