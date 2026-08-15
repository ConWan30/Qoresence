"""Tests for Phase 5.2: FPS profiles beyond CoD.

Verifies that Valorant, Apex Legends, and Fortnite profiles are
registered, have correct event vocabularies, and resolve via aliases.
"""

from __future__ import annotations

from qoresence.core.unified_config import (
    APEX_LEGENDS_PROFILE,
    CALL_OF_DUTY_PROFILE,
    FORTNITE_PROFILE,
    GAME_PROFILE_REGISTRY,
    VALORANT_PROFILE,
    GameProfileId,
    normalize_game_profile,
)

# ── Profile registration ─────────────────────────────────────────────────────


def test_valorant_profile_registered():
    assert GameProfileId.VALORANT in GAME_PROFILE_REGISTRY
    p = GAME_PROFILE_REGISTRY[GameProfileId.VALORANT]
    assert p.display_name == "Valorant"
    assert p.category == "shooter"


def test_apex_profile_registered():
    assert GameProfileId.APEX_LEGENDS in GAME_PROFILE_REGISTRY
    p = GAME_PROFILE_REGISTRY[GameProfileId.APEX_LEGENDS]
    assert p.display_name == "Apex Legends"
    assert p.category == "shooter"


def test_fortnite_profile_registered():
    assert GameProfileId.FORTNITE in GAME_PROFILE_REGISTRY
    p = GAME_PROFILE_REGISTRY[GameProfileId.FORTNITE]
    assert p.display_name == "Fortnite"
    assert p.category == "shooter"


def test_all_profiles_in_registry():
    assert len(GAME_PROFILE_REGISTRY) >= 5
    for pid in (
        GameProfileId.NCAA_FOOTBALL_27,
        GameProfileId.MADDEN_27,
        GameProfileId.CALL_OF_DUTY,
        GameProfileId.VALORANT,
        GameProfileId.APEX_LEGENDS,
        GameProfileId.FORTNITE,
    ):
        assert pid in GAME_PROFILE_REGISTRY


# ── Event vocabularies ───────────────────────────────────────────────────────


def test_valorant_has_spike_events():
    assert "spike_plant" in VALORANT_PROFILE.event_types
    assert "spike_defuse" in VALORANT_PROFILE.event_types
    assert "spike_detonate" in VALORANT_PROFILE.event_types
    assert "ace" in VALORANT_PROFILE.event_types
    assert "clutch" in VALORANT_PROFILE.event_types


def test_apex_has_ring_events():
    assert "ring_close" in APEX_LEGENDS_PROFILE.event_types
    assert "zone_damage" in APEX_LEGENDS_PROFILE.event_types
    assert "squad_wipe" in APEX_LEGENDS_PROFILE.event_types
    assert "champion" in APEX_LEGENDS_PROFILE.event_types
    assert "knockdown" in APEX_LEGENDS_PROFILE.event_types


def test_fortnite_has_storm_events():
    assert "storm_close" in FORTNITE_PROFILE.event_types
    assert "storm_damage" in FORTNITE_PROFILE.event_types
    assert "victory_royale" in FORTNITE_PROFILE.event_types
    assert "chest_open" in FORTNITE_PROFILE.event_types


def test_all_shooter_profiles_share_kill_death():
    for p in (CALL_OF_DUTY_PROFILE, VALORANT_PROFILE, APEX_LEGENDS_PROFILE, FORTNITE_PROFILE):
        assert "kill" in p.event_types, f"{p.profile_id} missing kill"
        assert "death" in p.event_types, f"{p.profile_id} missing death"
        assert "match_start" in p.event_types, f"{p.profile_id} missing match_start"
        assert "match_end" in p.event_types, f"{p.profile_id} missing match_end"


# ── Aliases ──────────────────────────────────────────────────────────────────


def test_valorant_aliases():
    assert normalize_game_profile("valorant") == GameProfileId.VALORANT
    assert normalize_game_profile("val") == GameProfileId.VALORANT


def test_apex_aliases():
    assert normalize_game_profile("apex") == GameProfileId.APEX_LEGENDS
    assert normalize_game_profile("apex_legends") == GameProfileId.APEX_LEGENDS


def test_fortnite_aliases():
    assert normalize_game_profile("fortnite") == GameProfileId.FORTNITE
    assert normalize_game_profile("fn") == GameProfileId.FORTNITE


def test_cod_extra_aliases():
    assert normalize_game_profile("mw2") == GameProfileId.CALL_OF_DUTY
    assert normalize_game_profile("mw3") == GameProfileId.CALL_OF_DUTY
    assert normalize_game_profile("bo6") == GameProfileId.CALL_OF_DUTY


# ── Outcome fields ───────────────────────────────────────────────────────────


def test_valorant_outcome_fields():
    assert "agent" in VALORANT_PROFILE.outcome_fields
    assert "spike_planted" in VALORANT_PROFILE.outcome_fields
    assert "credits" in VALORANT_PROFILE.outcome_fields
    assert "side" in VALORANT_PROFILE.outcome_fields


def test_apex_outcome_fields():
    assert "damage" in APEX_LEGENDS_PROFILE.outcome_fields
    assert "squad_count" in APEX_LEGENDS_PROFILE.outcome_fields
    assert "ring_phase" in APEX_LEGENDS_PROFILE.outcome_fields
    assert "legend" in APEX_LEGENDS_PROFILE.outcome_fields
    assert "placement" in APEX_LEGENDS_PROFILE.outcome_fields


def test_fortnite_outcome_fields():
    assert "players_alive" in FORTNITE_PROFILE.outcome_fields
    assert "storm_phase" in FORTNITE_PROFILE.outcome_fields
    assert "placement" in FORTNITE_PROFILE.outcome_fields
    assert "team_mode" in FORTNITE_PROFILE.outcome_fields
    assert "materials" in FORTNITE_PROFILE.outcome_fields
