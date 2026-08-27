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
    if phase == "huddle_offense":
        return "preplay_offense"
    elif phase == "huddle_defense":
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


def get_visual_phase_from_context(visual_context: dict[str, Any]) -> str | None:
    """Extract visual_phase from visual_context payload (fail-closed).

    Looks for visual_phase in:
    1. visual_context.details.visual_phase (preferred)
    2. visual_context.visual_phase (fallback)

    Args:
        visual_context: Visual context payload from VLM

    Returns:
        visual_phase string or None if not found
    """
    if not visual_context:
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
