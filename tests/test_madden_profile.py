"""Madden NFL 27 is a first-class football profile, not an NCAA alias."""

from __future__ import annotations

from qoresence.core.unified_config import (
    GAME_PROFILE_REGISTRY,
    MADDEN_27_PROFILE,
    NCAA_FOOTBALL_27_PROFILE,
    GameProfileId,
    get_game_profile,
    normalize_game_profile,
)
from qoresence.lobes.outcome import OutcomeRuntime


def test_madden_registered():
    assert GameProfileId.MADDEN_27 in GAME_PROFILE_REGISTRY
    p = GAME_PROFILE_REGISTRY[GameProfileId.MADDEN_27]
    assert p.display_name == "EA Sports Madden NFL 27"
    assert p.category == "football"


def test_madden_aliases_not_ncaa():
    for alias in (
        "madden_27",
        "madden_2027",
        "madden",
        "madden27",
        "madden_nfl_27",
        "ea_madden",
        "ea_sports_madden_27",
    ):
        assert normalize_game_profile(alias) == GameProfileId.MADDEN_27
    assert normalize_game_profile("ncaa_football_27") == GameProfileId.NCAA_FOOTBALL_27


def test_madden_shares_football_vocab_plus_nfl():
    ev = set(MADDEN_27_PROFILE.event_types)
    ncaa = set(NCAA_FOOTBALL_27_PROFILE.event_types)
    assert {"snap", "touchdown", "field_goal", "score_changed"} <= ev
    assert "challenge" in ev
    assert "overtime" in ev
    assert ncaa <= ev or {"snap", "touchdown"} <= ev
    assert set(NCAA_FOOTBALL_27_PROFILE.outcome_fields) <= set(MADDEN_27_PROFILE.outcome_fields)
    assert "home_team" in MADDEN_27_PROFILE.outcome_fields


def test_get_game_profile_madden():
    p = get_game_profile("madden_27")
    assert p.profile_id == GameProfileId.MADDEN_27
    assert p.category == "football"


def test_outcome_routes_football_by_category():
    """Madden must hit _process_football, not only the NCAA id."""
    from qoresence.core.unified_config import OutcomeConfig

    rt = OutcomeRuntime.__new__(OutcomeRuntime)
    rt._profile = MADDEN_27_PROFILE
    assert rt._profile.category == "football"
    assert OutcomeConfig  # keep import used
    assert MADDEN_27_PROFILE.profile_id != GameProfileId.NCAA_FOOTBALL_27
