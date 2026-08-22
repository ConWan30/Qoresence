"""
MomentScorer for ClutchBot.

Decides whether the current situation is worth a chat message, clip,
prediction, or other action. Phase 1 is rule- and template-driven. The design
is intentionally modular so a small LLM or learned scorer can be swapped in
later.
"""

from __future__ import annotations

import json
import logging
import math as _math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .helix_client import PredictionResult
from .situation_model import SituationState
from .win_probability import FootballWinProbability

log = logging.getLogger(__name__)

DEFAULT_FEATURES = frozenset({"chat"})


def _possession_label(state: SituationState) -> str:
    poss = state.possession or ""
    if poss == "home" and getattr(state, "home_team_name", None):
        return state.home_team_name
    if poss == "away" and getattr(state, "away_team_name", None):
        return state.away_team_name
    return poss


def _should_auto_clip_score(fields: dict[str, Any], state: SituationState, weight: float) -> bool:
    """Clip on a real confirm digit change — not the first 0-0 lock."""
    home = fields.get("home_score", state.home_score)
    away = fields.get("away_score", state.away_score)
    prev_h = fields.get("prev_home_score")
    prev_a = fields.get("prev_away_score")
    if prev_h is None and prev_a is None:
        if (home or 0) == 0 and (away or 0) == 0:
            return False
        return weight >= 0.8
    try:
        h = int(home) if home is not None else None
        a = int(away) if away is not None else None
        ph = int(prev_h) if prev_h is not None else None
        pa = int(prev_a) if prev_a is not None else None
    except (TypeError, ValueError):
        return False
    # Football scores only go up in a game. A drop is a VLM flicker / replay
    # graphic (live 2026-08-14: 17-21 → 10-7), not a clip.
    if ph is not None and h is not None and h < ph:
        return False
    if pa is not None and a is not None and a < pa:
        return False
    if ph is not None and h is not None and h != ph:
        return True
    if pa is not None and a is not None and a != pa:
        return True
    return False
