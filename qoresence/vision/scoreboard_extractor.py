"""Local scoreboard OCR + parsing for NCAA football frames.

Uses EasyOCR on a bottom-center crop and extracts score, quarter, clock,
down/distance, and play-clock from the HUD. No cloud VLM calls.

Score updates are **stabilized** (temporal consensus + plausible deltas) so a
single misread like 17-2 cannot wipe a real 17-17.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from qoresence.vision.visual_context import GameCategory, VisualContext

log = logging.getLogger(__name__)

# Football scoring increments (one team) — used for plausibility, not hard law
_PLAUSIBLE_SCORE_DELTAS = frozenset({0, 1, 2, 3, 6, 7, 8})


def _normalize_quarter_word(token: str) -> str:
    """Fix common OCR mis-reads for quarter/down tokens (Jst -> 1st, etc.)."""
    token = token.strip()
    if re.match(r"^[JjIiLlZz]st$", token, re.IGNORECASE):
        return "1st"
    if re.match(r"^[2Zz]nd$", token, re.IGNORECASE):
        return "2nd"
    if re.match(r"^[3Zz]rd$", token, re.IGNORECASE):
        return "3rd"
    if re.match(r"^[4A-Za-z]th$", token, re.IGNORECASE):
        # 4th is usually clear, but sometimes OCR drops the 4
        if token[0].lower() in "th":
            return "4th"
    return token


def _fix_digits_in(token: str) -> str:
    """Replace letters that look like digits, for short numeric tokens."""
    if re.search(r"[a-z]{2,}", token, re.IGNORECASE):
        return token
    mapping = str.maketrans(
        {
            "J": "1",
            "j": "1",
            "I": "1",
            "i": "1",
            "l": "1",
            "L": "1",
            "O": "0",
            "o": "0",
            "S": "5",
            "s": "5",
            "B": "8",
            "b": "8",
            "G": "6",
            "g": "6",
            "Z": "2",
            "z": "2",
            "T": "7",
            "t": "7",
            "|": "",
            ":": "",
        }
    )
    return token.translate(mapping)


_LOADING_STATES = frozenset({"loading", "cutscene", "intro", "replay"})
_MENU_STATES = frozenset({"menu", "paused", "lobby", "results", "spectating"})


def _game_state_token(ctx: VisualContext | None) -> str:
    if ctx is None:
        return ""
    try:
        return str(getattr(ctx.game_state, "value", None) or ctx.game_state or "").lower()
    except Exception:
        return ""
