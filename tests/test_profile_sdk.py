"""Tests for Phase 5.3: Community game-profile SDK."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from qoresence.core.unified_config import (
    GAME_PROFILE_ALIASES,
    GAME_PROFILE_REGISTRY,
    GameProfileId,
)


def test_load_community_profile_from_yaml():
    """A YAML file in profiles/ should be loaded and registered."""
    from qoresence.profiles.sdk import load_community_profiles

    with tempfile.TemporaryDirectory() as tmp:
        pdir = Path(tmp) / "profiles"
        pdir.mkdir()
        (pdir / "test_game.yaml").write_text(
            """
profile_id: test_game
display_name: Test Game
category: other
event_types:
  - jump
  - score
  - match_start
outcome_fields:
  - score
  - level
aliases:
  - tg
  - testgame
""",
            encoding="utf-8",
        )
        n = load_community_profiles(profiles_dir=pdir)
        assert n == 1

        # Profile should be in registry
        pids = [str(p) for p in GAME_PROFILE_REGISTRY]
        assert "test_game" in pids

        # Find the profile
        test_profile = None
        for pid, p in GAME_PROFILE_REGISTRY.items():
            if str(pid) == "test_game":
                test_profile = p
                break
        assert test_profile is not None
        assert test_profile.display_name == "Test Game"
        assert "jump" in test_profile.event_types
        assert "score" in test_profile.outcome_fields

        # Aliases should be registered
        assert "tg" in GAME_PROFILE_ALIASES
        assert "testgame" in GAME_PROFILE_ALIASES


def test_load_multiple_profiles():
    """Multiple YAML files should all be loaded."""
    from qoresence.profiles.sdk import load_community_profiles

    with tempfile.TemporaryDirectory() as tmp:
        pdir = Path(tmp) / "profiles"
        pdir.mkdir()
        (pdir / "game_a.yaml").write_text(
            "profile_id: game_a\ndisplay_name: Game A\ncategory: other\n"
            "event_types: [start, end]\noutcome_fields: [score]\n",
            encoding="utf-8",
        )
        (pdir / "game_b.yml").write_text(
            "profile_id: game_b\ndisplay_name: Game B\ncategory: shooter\n"
            "event_types: [kill, death]\noutcome_fields: [kills]\n",
            encoding="utf-8",
        )
        n = load_community_profiles(profiles_dir=pdir)
        assert n == 2


def test_invalid_yaml_skipped():
    """Invalid YAML should be skipped without crashing."""
    from qoresence.profiles.sdk import load_community_profiles

    with tempfile.TemporaryDirectory() as tmp:
        pdir = Path(tmp) / "profiles"
        pdir.mkdir()
        (pdir / "bad.yaml").write_text("not: a: valid: mapping: :::", encoding="utf-8")
        (pdir / "good.yaml").write_text(
            "profile_id: good_game\ndisplay_name: Good\n"
            "category: other\nevent_types: [start]\noutcome_fields: []\n",
            encoding="utf-8",
        )
        n = load_community_profiles(profiles_dir=pdir)
        assert n == 1  # only the good one


def test_missing_event_types_skipped():
    """A profile with no event_types should be skipped."""
    from qoresence.profiles.sdk import load_community_profiles

    with tempfile.TemporaryDirectory() as tmp:
        pdir = Path(tmp) / "profiles"
        pdir.mkdir()
        (pdir / "no_events.yaml").write_text(
            "profile_id: no_events\ndisplay_name: No Events\n"
            "category: other\nevent_types: []\noutcome_fields: [score]\n",
            encoding="utf-8",
        )
        n = load_community_profiles(profiles_dir=pdir)
        assert n == 0


def test_nonexistent_dir_returns_zero():
    """A nonexistent directory should return 0, not crash."""
    from qoresence.profiles.sdk import load_community_profiles

    n = load_community_profiles(profiles_dir="/nonexistent/path/xyz")
    assert n == 0


def test_list_profiles():
    """list_profiles should return all registered profiles."""
    from qoresence.profiles.sdk import list_profiles

    profiles = list_profiles()
    assert len(profiles) >= 5  # at least the 5 built-in profiles
    pids = [p["profile_id"] for p in profiles]
    assert "ncaa_football_27" in pids
    assert "call_of_duty" in pids
    assert "valorant" in pids
    # Check built-in flag
    for p in profiles:
        if p["profile_id"] == "ncaa_football_27":
            assert p["community"] is False


def test_community_profile_marked_as_community():
    """Community profiles should be marked community=True in list_profiles."""
    from qoresence.profiles.sdk import list_profiles, load_community_profiles

    with tempfile.TemporaryDirectory() as tmp:
        pdir = Path(tmp) / "profiles"
        pdir.mkdir()
        (pdir / "comm.yaml").write_text(
            "profile_id: comm_game\ndisplay_name: Community Game\n"
            "category: other\nevent_types: [start]\noutcome_fields: []\n",
            encoding="utf-8",
        )
        load_community_profiles(profiles_dir=pdir)
        profiles = list_profiles()
        comm = [p for p in profiles if p["profile_id"] == "comm_game"]
        assert len(comm) == 1
        assert comm[0]["community"] is True


def test_rocket_league_example_loads():
    """The bundled rocket_league.yaml example should load successfully."""
    from qoresence.profiles.sdk import load_community_profiles

    rl_path = Path("profiles/rocket_league.yaml")
    if not rl_path.exists():
        pytest.skip("rocket_league.yaml not found (running from different cwd)")
    n = load_community_profiles(profiles_dir="profiles")
    assert n >= 1
    pids = [str(p) for p in GAME_PROFILE_REGISTRY]
    assert "rocket_league" in pids
