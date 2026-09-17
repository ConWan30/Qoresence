"""Gamer honesty speech — closed sentences, never operator why_strip.

Theater / Session Now only. Never Lens. Never licenses score digits.
Inverse of ScoreboardOCR last-good: blank is the product.
"""

from __future__ import annotations

from typing import Any

# Presence is join density, not clutch / highlight.
PRESENCE_SPEECH = {
    "idle": "Pad and picture quiet",
    "join": "Pad and picture together",
    "dense": "Pad and picture dense — local clip possible",
}

HONESTY_SPEECH = {
    "ok": "",
    "amber": "Board uncertain — holding blank",
    "void": "Board not licensed yet",
    "ident": "Would rather go blank than keep a stale score",
}


def gamer_honesty_speech(
    *,
    honesty_band: str | None = None,
    presence_token: str | None = None,
    ident_now: bool = False,
    board_speech: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Closed copy for Now / Theater. Empty line when licensed and honest."""
    if not enabled:
        return {
            "line": "",
            "presence": "",
            "ident": False,
            "licenses_digits": False,
        }
    band = str(honesty_band or "").strip().lower()
    if ident_now:
        band = "ident"
    if band not in HONESTY_SPEECH:
        band = "void"
    token = str(presence_token or "").strip().lower()
    if token not in PRESENCE_SPEECH:
        token = "idle"
    line = HONESTY_SPEECH[band]
    if not line and board_speech and board_speech not in {"confirm_ticket", ""}:
        from qoresence.vision.board_why import gamer_board_speech

        line = gamer_board_speech(board_speech)
    return {
        "line": line,
        "presence": PRESENCE_SPEECH[token],
        "ident": band == "ident",
        "licenses_digits": False,
        "band": band,
        "token": token,
    }
