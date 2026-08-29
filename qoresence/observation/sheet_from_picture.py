"""Visual phase → control sheet mapper (observation plane only).

Maps picture-language phase signals (e.g. visual_context.details.visual_phase)
to the EA control sheet key for Madden 27 or College Football 27.

Fail-closed: unknown/missing/garbage phase → None.
Wrong title profile → None.
Menu/lobby/replay → None.

Used by MaddenControlLookup and CfbControlLookup to select the active control sheet.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Allowlist of visual_phase values (picture language, not pad language)
VISUAL_PHASE_ALLOWLIST = frozenset(
    {
        "huddle_offense",
        "huddle_defense",
        "snap",
        "running",
        "passing",
        "ball_in_air",
        "coverage",
        "defense_pursuit",
        "defense_engaged",
        "blocking",
        "player_locked_receiver",
        "offense",  # Generic offense from possession
        "defense",  # Generic defense from possession
    }
)

# Madden 27 sheet keys (10 sheets)
MADDEN_SHEETS = frozenset(
    {
        "ball_in_air",
        "blocking",
        "defense_engaged",
        "defense_pursuit",
        "defensive_coverage",
        "passing",
        "player_locked_receiver",
        "preplay_defense",
        "preplay_offense",
        "running",
    }
)

# College Football 27 sheet keys (10 sheets)
CFB_SHEETS = frozenset(
    {
        "ball_in_air",
        "blocking_mechanics",
        "defense_engaged",
        "defense_pursuit",
        "defensive_coverage_mechanics",
        "passing",
        "player_locked_receiver",
        "preplay_defense",
        "preplay_offense",
        "running",
    }
)


def map_visual_phase_to_sheet(
    visual_phase: str | None,
    game_profile: str | None,
) -> str | None:
    """Map visual_phase (picture language) to EA control sheet key (pad language).

    Args:
        visual_phase: Picture phase signal (e.g. "huddle_offense", "running")
        game_profile: Game profile id (e.g. "madden_27", "ncaa_football_27")

    Returns:
        Sheet key (e.g. "preplay_offense", "running") or None if cannot map

    Mapping (fail-closed):
        huddle_offense → preplay_offense
        huddle_defense → preplay_defense
        snap → preplay_offense (snap happens during preplay)
        running → running
        passing → passing
        ball_in_air → ball_in_air
        coverage → defensive_coverage (Madden) / defensive_coverage_mechanics (CFB)
        defense_pursuit → defense_pursuit
        defense_engaged → defense_engaged
        blocking → blocking (Madden) / blocking_mechanics (CFB)
        player_locked_receiver → player_locked_receiver

        Unknown/missing/garbage → None
    """
    if visual_phase is None or game_profile is None:
        return None

    phase = str(visual_phase).strip().lower()
    profile = str(game_profile).strip().lower()

    # Check allowlist (fail-closed)
    if phase not in VISUAL_PHASE_ALLOWLIST:
        return None

    # Detect game (Madden vs CFB)
    is_madden = "madden" in profile
    is_cfb = any(x in profile for x in ["cfb", "college", "ncaa"])

    if not is_madden and not is_cfb:
        # Wrong title profile → None
        return None

    # Map picture phase to sheet key
    if phase == "huddle_offense" or phase == "offense":
        return "preplay_offense"
    elif phase == "huddle_defense" or phase == "defense":
        return "preplay_defense"
    elif phase == "snap":
        # Snap happens during preplay (before ball is snapped)
        return "preplay_offense"
    elif phase == "running":
        return "running"
    elif phase == "passing":
        return "passing"
    elif phase == "ball_in_air":
        return "ball_in_air"
    elif phase == "coverage":
        # CFB uses "defensive_coverage_mechanics", Madden uses "defensive_coverage"
        return "defensive_coverage_mechanics" if is_cfb else "defensive_coverage"
    elif phase == "defense_pursuit":
        return "defense_pursuit"
    elif phase == "defense_engaged":
        return "defense_engaged"
    elif phase == "blocking":
        # CFB uses "blocking_mechanics", Madden uses "blocking"
        return "blocking_mechanics" if is_cfb else "blocking"
    elif phase == "player_locked_receiver":
        return "player_locked_receiver"

    # Should never reach here (allowlist check above), but fail-closed anyway
    return None


def infer_offense_defense_from_possession(
    scoreboard_data: dict[str, Any] | None,
    is_home_team: bool,
) -> str | None:
    """Infer offense or defense phase from scoreboard possession (fail-closed).

    Args:
        scoreboard_data: Scoreboard VLM result with possession_side and home_left
        is_home_team: True if we're controlling the home team, False for away

    Returns:
        "offense" or "defense" or None if cannot determine

    Logic:
        - possession_side (left|right) + home_left tells us who has the ball
        - If we're the team with the ball → offense, else defense
        - If possession_side is null/missing → None (fail-closed)
    """
    if not scoreboard_data:
        return None

    possession_side = scoreboard_data.get("possession_side")
    home_left = scoreboard_data.get("home_left")

    # Fail-closed: missing possession or home_left
    if possession_side is None or home_left is None:
        return None

    # Determine which side (left/right) is the home team
    home_side = "left" if home_left else "right"
    away_side = "right" if home_left else "left"

    # Determine which side has possession
    if possession_side not in {"left", "right"}:
        return None

    # If we're home team
    if is_home_team:
        return "offense" if possession_side == home_side else "defense"
    else:  # we're away team
        return "offense" if possession_side == away_side else "defense"


def get_visual_phase_from_context(visual_context: dict[str, Any] | Any) -> str | None:
    """Extract visual_phase from visual_context payload (fail-closed).

    Looks for visual_phase in:
    1. visual_context.details.visual_phase (preferred)
    2. visual_context.visual_phase (fallback)
    
    Coerces VisualContext dataclass to dict automatically.

    Args:
        visual_context: Visual context payload from VLM or VisualContext dataclass

    Returns:
        visual_phase string or None if not found
    """
    if not visual_context:
        return None
    
    # Coerce VisualContext dataclass to dict if needed
    if not isinstance(visual_context, dict):
        if hasattr(visual_context, "to_dict"):
            try:
                visual_context = visual_context.to_dict()
            except Exception:
                return None
        elif hasattr(visual_context, "details"):
            # Try to read details directly from dataclass
            try:
                details = getattr(visual_context, "details", None)
                if isinstance(details, dict) and "visual_phase" in details:
                    vp = details.get("visual_phase")
                    if vp is not None:
                        return str(vp).strip().lower()
            except Exception:
                pass
            return None
        else:
            return None

    # Preferred: details.visual_phase
    details = visual_context.get("details")
    if isinstance(details, dict):
        vp = details.get("visual_phase")
        if vp is not None:
            return str(vp).strip().lower()

    # Fallback: top-level visual_phase
    vp = visual_context.get("visual_phase")
    if vp is not None:
        return str(vp).strip().lower()

    return None


def map_context_to_sheet(visual_context: dict[str, Any]) -> str | None:
    """Map visual_context to EA control sheet key (fail-closed).

    Convenience wrapper that extracts visual_phase and game_profile from
    visual_context and calls map_visual_phase_to_sheet.

    Args:
        visual_context: Visual context payload

    Returns:
        Sheet key or None if cannot map
    """
    if not visual_context:
        return None

    # Extract game_profile
    game_profile = visual_context.get("game_profile")

    # Extract visual_phase
    visual_phase = get_visual_phase_from_context(visual_context)

    # Map to sheet
    return map_visual_phase_to_sheet(visual_phase, game_profile)
