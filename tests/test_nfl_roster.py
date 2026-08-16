"""NFL roster matching for Madden 27 — no invented names."""

from __future__ import annotations

import json
from pathlib import Path

from qoresence.profiles.nfl_roster import (
    NflRosterIndex,
    apply_roster_to_context,
    is_madden_profile,
    parse_nameplate,
)
from qoresence.vision.visual_context import VisualContext


def _index(tmp_path: Path) -> NflRosterIndex:
    roster = tmp_path / "roster.jsonl"
    rows = [
        {
            "full_name": "Patrick Mahomes",
            "last_name": "Mahomes",
            "football_name": "P.Mahomes",
            "jersey_number": "15",
            "position": "QB",
            "team": "KC",
        },
        {
            "full_name": "Travis Kelce",
            "last_name": "Kelce",
            "football_name": "T.Kelce",
            "jersey_number": "87",
            "position": "TE",
            "team": "KC",
        },
        {
            "full_name": "Jalen Hurts",
            "last_name": "Hurts",
            "football_name": "J.Hurts",
            "jersey_number": "1",
            "position": "QB",
            "team": "PHI",
        },
        {
            "full_name": "A.J. Brown",
            "last_name": "Brown",
            "football_name": "A.Brown",
            "jersey_number": "11",
            "position": "WR",
            "team": "PHI",
        },
        {
            "full_name": "Marquise Brown",
            "last_name": "Brown",
            "football_name": "M.Brown",
            "jersey_number": "5",
            "position": "WR",
            "team": "KC",
        },
    ]
    roster.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return NflRosterIndex.load(roster_path=roster)


def test_is_madden_profile():
    assert is_madden_profile("madden_27") is True
    assert is_madden_profile("ncaa_football_27") is False


def test_team_aliases():
    idx = NflRosterIndex.load(roster_path=Path("no/such.jsonl"))
    assert idx.match_team("KC").abbr == "KC"
    assert idx.match_team("Chiefs").nick == "Chiefs"
    assert idx.match_team("Kansas City").abbr == "KC"
    assert idx.match_team("JAX").abbr == "JAX"
    assert idx.match_team("JAC").abbr == "JAX"
    assert idx.match_team("Louisville") is None
    assert idx.match_team("New York") is None  # Giants vs Jets


def test_player_jersey_plus_team(tmp_path: Path):
    idx = _index(tmp_path)
    p = idx.match_player("15 MAHOMES", team="KC")
    assert p is not None
    assert p.full_name == "Patrick Mahomes"
    assert idx.match_player(jersey=87, team="KC").full_name == "Travis Kelce"


def test_ambiguous_last_name_no_invent(tmp_path: Path):
    idx = _index(tmp_path)
    assert idx.match_player(last_name="Brown", team="PHI").full_name == "A.J. Brown"
    # last name only, two Browns in the league slice — refuse
    assert idx.match_player(last_name="Brown") is None
    assert idx.match_player("SMITH", team="KC") is None


def test_nameplate_ambiguous_flag(tmp_path: Path):
    idx = _index(tmp_path)
    from qoresence.profiles import nfl_roster as nr

    nr._index = idx
    hit = VisualContext(game_profile="madden_27")
    apply_roster_to_context(
        hit, {"home_team_raw": "Chiefs", "away_team_raw": "Eagles", "player_name": "15 Mahomes"}
    )
    assert hit.on_screen_player == "Patrick Mahomes"
    assert hit.nameplate_ambiguous is False
    amb = VisualContext(game_profile="madden_27")
    apply_roster_to_context(amb, {"player_name": "Brown"})
    assert amb.on_screen_player is None
    assert amb.nameplate_ambiguous is True
    miss = VisualContext(game_profile="madden_27")
    apply_roster_to_context(miss, {"home_team_raw": "Chiefs"})
    assert miss.on_screen_player is None
    assert miss.nameplate_ambiguous is False
    ncaa = VisualContext(game_profile="ncaa_football_27")
    apply_roster_to_context(ncaa, {"player_name": "Brown"})
    assert ncaa.on_screen_player is None
    assert ncaa.nameplate_ambiguous is False


def test_nameplate_parse():
    assert parse_nameplate("15 MAHOMES")["jersey"] == 15
    assert parse_nameplate("P. Mahomes")["last"].lower() == "mahomes"


def test_apply_only_on_madden(tmp_path: Path):
    idx = _index(tmp_path)
    from qoresence.profiles import nfl_roster as nr

    nr._index = idx
    ncaa = VisualContext(game_profile="ncaa_football_27")
    apply_roster_to_context(ncaa, {"home_team_raw": "Chiefs", "away_team_raw": "Eagles"})
    assert ncaa.home_team is None
    mad = VisualContext(game_profile="madden_27")
    apply_roster_to_context(mad, {"home_team_raw": "Chiefs", "away_team_raw": "Eagles"})
    assert mad.home_team == "KC"
    assert mad.away_team == "PHI"
    assert mad.home_team_name == "Kansas City Chiefs"


def test_resolve_possession_and_player(tmp_path: Path):
    idx = _index(tmp_path)
    out = idx.resolve(
        home_raw="Chiefs",
        away_raw="Eagles",
        possession="home",
        nameplate="15 Mahomes",
    )
    assert out["home_team"]["abbr"] == "KC"
    assert out["possession_team"]["nick"] == "Chiefs"
    assert out["on_screen_player"]["full_name"] == "Patrick Mahomes"
