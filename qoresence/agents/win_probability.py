"""
Football Win Probability model.

Defensible, dependency-free approximation inspired by public CFB/NFL
Expected Points and Win Probability research. No external deps beyond stdlib.

Public CFB EP observations (approx):
- EP is ~ linear with field position, ~0 at own 20, ~2 at midfield,
  ~4-5 inside opp 10. We encode a bucket table and interpolate.
- WP uses a logistic on score_diff + field advantage + time remaining.

OT and end-of-half are handled as edge cases.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Expected Points table
# ---------------------------------------------------------------------------
# Key = yards to opponent endzone (0 = goal line, 99 = own 1). Value = EP for
# the possession team. Approximated from public CFB data (e.g., CFBD / nflfastR).
# Own 1 (~99 yd away) is negative EP; Opp goal line (~1 yd away) is ~6 EP.
FOOTBALL_EP_TABLE: dict[int, float] = {
    99: -1.5,
    95: -0.5,
    90: 0.0,
    80: 0.5,
    70: 1.2,
    60: 1.8,
    50: 2.2,
    40: 3.0,
    30: 3.8,
    20: 4.3,
    15: 4.9,
    10: 5.4,
    5: 6.0,
    2: 6.4,
    1: 6.8,
}

# Sorted keys for interpolation
_EP_SORTED = sorted(FOOTBALL_EP_TABLE.items())  # list of (yds_to_opp, ep)


def parse_field_position(field_position: str | None) -> int | None:
    """
    Parse a field_position string like "opp 10", "own 45", "opponent 15"
    into yards to opponent endzone (int 1-99).

    Returns None if unparsable / empty.

    Handles:
      "opp 10"       -> 10
      "opponent 15"  -> 15
      "own 45"       -> 55  (100-45)
      "own 20"       -> 80
      "midfield" / "50" -> 50
      "opp 35"       -> 35
    Case-insensitive, tolerant of extra whitespace.
    """
    if not field_position:
        return None
    s = field_position.strip().lower()
    if not s:
        return None
    if "midfield" in s or s == "50" or s == "mid":
        return 50

    # Try "opp 10" / "opponent 10"
    m = re.search(r"opp(?:onent)?\s*(\d+)", s)
    if m:
        v = int(m.group(1))
        return max(1, min(99, v))

    # Try "own 45"
    m = re.search(r"own\s*(\d+)", s)
    if m:
        v = int(m.group(1))
        # own 45 means 55 away from opp endzone
        yds_to_opp = 100 - v
        return max(1, min(99, yds_to_opp))

    # Bare number like "30" or "opp10" without space - try any int
    m = re.search(r"(\d+)", s)
    if m:
        # ambiguous - assume yards to opp if no qualifier; clamp
        v = int(m.group(1))
        if 1 <= v <= 99:
            return v

    return None


def _ep_for_yards(yds_to_opp: int | None) -> float:
    """Interpolate EP for a given yards-to-opp. Returns 0 if unknown."""
    if yds_to_opp is None:
        return 0.0
    yds_to_opp = max(1, min(99, int(yds_to_opp)))

    # exact hit
    if yds_to_opp in FOOTBALL_EP_TABLE:
        return FOOTBALL_EP_TABLE[yds_to_opp]

    # linear interpolation between nearest buckets
    lower = None
    upper = None
    for y, ep in _EP_SORTED:
        if y < yds_to_opp:
            lower = (y, ep)
        elif y > yds_to_opp and upper is None:
            upper = (y, ep)
            break

    if lower is None:
        return upper[1] if upper else 0.0
    if upper is None:
        return lower[1]
    # interpolate: y between lower and upper
    y0, ep0 = lower
    y1, ep1 = upper
    frac = (yds_to_opp - y0) / (y1 - y0) if y1 != y0 else 0
    # Note: table is decreasing EP as yds increases, but sorted ascending
    # For yds_to_opp larger means lower EP, so interpolation is linear.
    return ep0 + frac * (ep1 - ep0)


def _sigmoid(x: float) -> float:
    # clamp to avoid overflow
    if x > 20:
        return 1.0
    if x < -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


class FootballWinProbability:
    """
    Simple football Win Probability model.

    Usage:
        wp = FootballWinProbability()
        result = wp.compute(state_dict)
        # result = {"win_prob": 0.73, "expected_points": 2.2, "wp_swing": 0.04, ...}
    """

    def __init__(self) -> None:
        self._prev_win_prob: float | None = None
        self._prev_state: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def calibrate(self, samples: list[dict[str, Any]] | None = None) -> None:
        """Placeholder for future calibration against labelled data."""
        # Intended to fit logistic coefficients via MLE. No-op for now.
        return

    def reset(self) -> None:
        self._prev_win_prob = None
        self._prev_state = None

    def compute(self, state: dict[str, Any] | Any) -> dict[str, Any]:
        """
        Compute win probability for a situation.

        Args:
            state: dict or SituationState-like object with keys/attrs:
              quarter (1-4, 5+ = OT), clock_seconds (remaining in quarter),
              down, yards_to_go, yardline/field_position/yards_to_opp,
              score_diff (possession minus opponent), possession

        Returns:
            dict with win_prob (0-1), expected_points, wp_swing,
            yds_to_opp, total_seconds_remaining
        """
        # Normalize to dict
        if not isinstance(state, dict):
            # Attempt to extract from SituationState or similar
            state = self._coerce_state(state)

        quarter = state.get("quarter")
        clock_seconds = state.get("clock_seconds")
        # also support alternate keys
        if clock_seconds is None:
            clock_seconds = state.get("game_clock_seconds")
        if clock_seconds is None:
            clock_seconds = state.get("clock")
        down = state.get("down")
        ytg = state.get("yards_to_go")
        field_position = state.get("field_position")
        yardline = state.get("yardline")
        yds_to_opp = state.get("yards_to_opp")
        if yds_to_opp is None and yardline is not None:
            try:
                yds_to_opp = int(yardline)
            except Exception:
                yds_to_opp = None
        if yds_to_opp is None:
            # try parse field_position
            if field_position is not None:
                yds_to_opp = parse_field_position(str(field_position))
            elif yardline is not None:
                yds_to_opp = parse_field_position(str(yardline))

        score_diff = state.get("score_diff")
        if score_diff is None:
            # try home/away
            hs = state.get("home_score")
            aw = state.get("away_score")
            possession = state.get("possession")
            if hs is not None and aw is not None and possession is not None:
                try:
                    hs = int(hs)
                    aw = int(aw)
                    # interpret possession: "home"/"away" -> score_diff for possession team
                    poss_lower = str(possession).lower()
                    if "home" in poss_lower:
                        score_diff = hs - aw
                    elif "away" in poss_lower:
                        score_diff = aw - hs
                    else:
                        # fallback: assume home perspective
                        score_diff = hs - aw
                except Exception:
                    score_diff = 0
            else:
                score_diff = state.get("score_diff", 0) or 0
        try:
            score_diff = float(score_diff) if score_diff is not None else 0.0
        except Exception:
            score_diff = 0.0

        # Defaults
        try:
            quarter = int(quarter) if quarter is not None else 1
        except Exception:
            quarter = 1
        try:
            clock_seconds = int(clock_seconds) if clock_seconds is not None else 15 * 60
        except Exception:
            clock_seconds = 15 * 60
        clock_seconds = max(0, min(15 * 60, clock_seconds))

        # Expected Points
        expected_points = _ep_for_yards(yds_to_opp)
        # small down/distance adjustment: obvious passing downs slightly lower EP?
        if down is not None and ytg is not None:
            try:
                d = int(down)
                y = int(ytg)
                if d == 3 and y >= 7:
                    expected_points -= 0.6
                elif d == 4:
                    expected_points -= 1.0
                elif d == 1 and y == 10 and yds_to_opp and yds_to_opp > 50:
                    expected_points += 0.2
            except Exception:
                pass

        # OT handling
        is_ot = quarter >= 5
        if is_ot:
            # OT: WP dominated by score_diff and field position; time is less relevant
            # Calibration: OT win prob ~ 0.55 per 3-point lead, strong field position boost
            logit = 0.55 * score_diff + 0.12 * expected_points
            # slight possession advantage for ball holder in OT
            logit += 0.15
            win_prob = _sigmoid(logit)
        else:
            # Regulation
            # Total seconds remaining estimate
            # Each quarter 15*60 = 900s
            quarters_remaining = max(0, 4 - quarter)
            total_remaining = quarters_remaining * 15 * 60 + clock_seconds
            # End-of-half tweak: if quarter==2 and clock small, reduce effective time pressure
            # because half ends; trailing teams get locker room reset.
            if quarter == 2 and clock_seconds < 120 and abs(score_diff) <= 7:
                # dampen score_diff impact slightly at end of half
                total_remaining = total_remaining * 0.9

            t_norm = total_remaining / 3600.0  # 0..1
            # score coefficient larger late, smaller early
            coeff = 0.12 + 0.18 * (1 - t_norm)  # 0.12 early, 0.30 late
            logit = coeff * score_diff * 3.5  # scale to make 14-pt lead ~ high WP late
            # Alternative simpler: logit = (0.35 - 0.15*t_norm) * score_diff
            # Use above coeff*3.5 to approximate that

            # More direct formula to keep defensible:
            # logit_score = (0.36 - 0.18 * t_norm) * score_diff  0.36 late, 0.18 early
            logit_score = (0.36 - 0.18 * t_norm) * score_diff
            logit = logit_score

            # Field position adds EP/7 * time-dampened
            # Early game EP matters less; late it matters more for scoring chance
            ep_weight = 0.18 * (1 - 0.4 * t_norm)
            logit += ep_weight * expected_points

            # Possession bonus tiny
            logit += 0.05

            win_prob = _sigmoid(logit)

        # Clamp
        win_prob = max(0.01, min(0.99, win_prob))

        # wp_swing vs prev
        if self._prev_win_prob is None:
            wp_swing = 0.0
        else:
            wp_swing = win_prob - self._prev_win_prob

        self._prev_win_prob = win_prob
        self._prev_state = dict(state) if isinstance(state, dict) else {"quarter": quarter, "clock_seconds": clock_seconds}

        return {
            "win_prob": win_prob,
            "expected_points": expected_points,
            "wp_swing": wp_swing,
            "yds_to_opp": yds_to_opp,
            "total_seconds_remaining": total_remaining if not is_ot else 0,
            "score_diff": score_diff,
            "is_ot": is_ot,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_state(obj: Any) -> dict[str, Any]:
        """Coerce a SituationState or generic object to dict."""
        if isinstance(obj, dict):
            return obj
        # Try dataclass / object attrs
        d: dict[str, Any] = {}
        for key in ("quarter", "clock_seconds", "game_clock_seconds", "down", "yards_to_go", "field_position", "yardline", "yards_to_opp", "score_diff", "home_score", "away_score", "possession", "clock", "play_clock"):
            if hasattr(obj, key):
                try:
                    d[key] = getattr(obj, key)
                except Exception:
                    pass
        # Also try .to_dict() if available
        if not d and hasattr(obj, "to_dict"):
            try:
                return obj.to_dict()
            except Exception:
                pass
        return d
