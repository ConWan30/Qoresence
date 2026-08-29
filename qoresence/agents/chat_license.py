"""Outbound chat license — ticket or score lock, else silence.

Phase 1 of clock-licensed actuators. Observation plane only.
"""

from __future__ import annotations

from typing import Any


def outbound_chat_allowed(
    *,
    path: str,
    coupling_ticket: Any | None = None,
    confirm_ticket: Any | None = None,
    score_vlm_locked: bool = False,
    picture_ticket: Any | None = None,
) -> bool:
    """Fast chat needs a coupling ticket or picture-HID label. Confirm needs a ticket or VLM lock."""
    kind = str(path or "").strip().lower()
    if kind == "fast":
        return coupling_ticket is not None or picture_ticket is not None
    if kind == "confirm":
        return confirm_ticket is not None or bool(score_vlm_locked)
    return False


def license_gate(
    *,
    path: str,
    ticket_id: str = "",
    coupling_ticket: Any | None = None,
    confirm_ticket: Any | None = None,
    score_vlm_locked: bool = False,
    picture_ticket: Any | None = None,
) -> bool:
    """Phase 3: no Quicksilver / A2A call without a ticket_id."""
    if not str(ticket_id or "").strip():
        return False
    return outbound_chat_allowed(
        path=path,
        coupling_ticket=coupling_ticket,
        confirm_ticket=confirm_ticket,
        score_vlm_locked=score_vlm_locked,
        picture_ticket=picture_ticket,
    )
