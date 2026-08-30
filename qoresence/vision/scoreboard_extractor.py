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
        # Contains a word, don't mangle it
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


def _may_mint_lock(ctx: VisualContext | None, vlm: dict[str, Any] | None = None) -> bool:
    """New locks during gameplay, or on football HUD when classifier says menu.

    Play-call / pause still paints the match scorebug. Refusing mint there
    left confirm empty while DeepSeek already had NO 0 / DAL 10.

    OPERATOR LAW: Refuse lock on loading/cutscene (garbage boards during matchup swap).
    """
    if ctx is None:
        return False
    gst = _game_state_token(ctx)
    if gst in _LOADING_STATES:
        return False
    if gst in {"", "gameplay", "playing", "in_game"}:
        return True
    if not _vlm_board_grounded(vlm):
        return False
    profile = str(getattr(ctx, "game_profile", "") or "").lower()
    title = str(getattr(ctx, "game_title", "") or "").lower()
    return any(k in profile or k in title for k in ("madden", "cfb", "football", "ncaa"))


def garbage_lock_reason(
    *,
    home: int,
    away: int,
    home_team: str = "",
    away_team: str = "",
    game_state: str = "",
    book: Any = None,
) -> str | None:
    """Why this pair must not mint. None = lock may proceed.

    Receipt 1.1: refuse 0-0 after identity swap (not every 0-0), refuse 82-86-class
    first locks, refuse a live-identity ticker swap (9-47 DAL-DET over IND-DET).
    """
    gst = str(game_state or "").lower()
    if gst in _LOADING_STATES:
        return "game_state"
    if _ScoreStabilizer._looks_suspicious_pair((home, away)):
        return "suspicious_pair"

    if book is None:
        try:
            from qoresence.vision.confirm_ticket import get_ticket_book

            book = get_ticket_book()
        except Exception:
            book = None
    ident = book.last_board_identity() if book is not None else None
    stale = bool(book.identity_stale()) if book is not None else False
    ht = str(home_team or "").strip()
    at = str(away_team or "").strip()

    if ident is not None:
        prior_h, prior_a, prior_ht, prior_at = ident
        teams_changed = False
        if prior_ht and prior_at and ht and at:
            try:
                from qoresence.vision.confirm_ticket import board_sides_same

                teams_changed = not board_sides_same(prior_ht, prior_at, ht, at)
            except Exception:
                prior_pair = {prior_ht.strip().upper(), prior_at.strip().upper()}
                now_pair = {ht.strip().upper(), at.strip().upper()}
                teams_changed = prior_pair != now_pair
        if home == 0 and away == 0:
            if teams_changed:
                return "zero_zero_after_identity_swap"
            if (prior_h or 0) > 0 or (prior_a or 0) > 0:
                return "zero_zero_after_nonzero"
        if teams_changed and not stale:
            return "identity_swap"

    if home == 0 and away == 0 and gst in _MENU_STATES:
        return "zero_zero_menu"
    return None


def _read_vlm_status() -> str:
    try:
        from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

        return str(get_scoreboard_vlm().vlm_status() or "none")
    except Exception:
        return "none"


def _stamp_board_why(ctx: VisualContext | None, why: str) -> str:
    """Record last refuse/license on ctx and a process-small last-why. No bus emit."""
    from qoresence.vision.board_why import normalize_board_why

    token = normalize_board_why(why)
    FootballScoreboardExtractor._last_board_why = token
    if ctx is None:
        return token
    ctx.board_why = token
    if not isinstance(ctx.details, dict):
        ctx.details = {}
    ctx.details["board_why"] = token
    return token
