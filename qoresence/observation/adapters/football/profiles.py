"""CFB vs Madden profile honesty — HUD hints and known blind spots."""

from __future__ import annotations

_SHARED_BLIND_SPOTS: tuple[str, ...] = (
    "snap alone does not open a play interval",
    "visual_phase boundaries are detector-time estimates, not frame-exact",
    "play outcome is never inferred from pixels in this adapter",
    "DualSense PS5 HID is not joined unless separately observed on this host",
    "scoreboard confirmation is historical only — not play-outcome causation",
)

_CFB_BLIND_SPOTS: tuple[str, ...] = (
    "CFB scorebug huddle may classify as menu without title-presence lock",
    "college ticker OCR can mis-route profile when game_title is empty",
    "defensive_coverage_mechanics sheet differs from Madden defensive_coverage",
)

_MADDEN_BLIND_SPOTS: tuple[str, ...] = (
    "challenge and overtime UI are outside the visual_phase allowlist",
    "NFL abbrev gate may refuse stranger scoreboard pairs",
    "Madden preplay_offense/defense sheets differ from CFB mechanics naming",
)

_CFB_HUD = {
    "scorebug": "upper_center",
    "play_clock": "upper_right",
    "down_distance": "lower_center",
    "possession": "scorebug_inline",
}

_MADDEN_HUD = {
    "scorebug": "upper_center",
    "play_clock": "upper_right",
    "down_distance": "lower_center",
    "timeouts": "upper_left",
}


def _profile_family(profile: str | None) -> str:
    p = str(profile or "").lower()
    if "madden" in p or p == "nfl":
        return "madden"
    if any(token in p for token in ("cfb", "ncaa", "college")):
        return "cfb"
    return "shared"


def hud_regions(profile: str | None) -> dict[str, str]:
    family = _profile_family(profile)
    if family == "madden":
        return dict(_MADDEN_HUD)
    if family == "cfb":
        return dict(_CFB_HUD)
    return dict(_CFB_HUD)


def blind_spots(profile: str | None) -> tuple[str, ...]:
    family = _profile_family(profile)
    spots = list(_SHARED_BLIND_SPOTS)
    if family == "cfb":
        spots.extend(_CFB_BLIND_SPOTS)
    elif family == "madden":
        spots.extend(_MADDEN_BLIND_SPOTS)
    else:
        spots.append("title profile unknown — shared football rules only")
    return tuple(spots)
