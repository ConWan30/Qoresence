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
) -> bool:
    """Fast chat needs a coupling ticket. Confirm needs a ticket or VLM lock."""
    kind = str(path or "").strip().lower()
    if kind == "fast":
        return coupling_ticket is not None
    if kind == "confirm":
        return confirm_ticket is not None or bool(score_vlm_locked)
    return False
