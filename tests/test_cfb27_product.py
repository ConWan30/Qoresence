"""CFB 27 product bar: this-match lock, huddle-as-gameplay, auditor tickets."""

from __future__ import annotations

from qoresence.profiles.cfb27_product import (
    effective_game_state,
    identity_compatible,
    identity_sides_stable,
    vlm_home_away_names,
)


def test_huddle_menu_becomes_gameplay_when_board_locked():
    assert effective_game_state("menu", locked=True, quarter=1, down=1) == "gameplay"
    assert effective_game_state("replay", locked=True, quarter=1, down=1) == "replay"
    assert effective_game_state("paused", locked=True, quarter=1) == "paused"
    assert effective_game_state("menu", locked=False) == "menu"


def test_identity_sticks_against_ticker_pair():
    assert identity_compatible("LOU", "OU", "Louisville", "Oklahoma") is True
    assert identity_compatible("LOU", "OU", "Oregon", "Wisconsin") is False
    assert identity_compatible("LOU", "OU", None, None) is True
    assert identity_compatible(None, None, "ORE", "WIS") is True


def test_madden_identity_sticks_against_nfl_ticker():
    assert identity_compatible("KC", "PHI", "Chiefs", "Eagles", profile="madden_27") is True
    assert identity_compatible("KC", "PHI", "Ravens", "Bengals", profile="madden_27") is False


def test_locked_pair_does_not_swap_sides_on_home_left_flicker():
    assert identity_compatible("KC", "PHI", "Eagles", "Chiefs", profile="madden_27") is True
    assert identity_sides_stable("KC", "PHI", "Chiefs", "Eagles", profile="madden_27") is True
    assert identity_sides_stable("KC", "PHI", "Eagles", "Chiefs", profile="madden_27") is False
    assert identity_sides_stable("KC", "PHI", None, None, profile="madden_27") is True
    assert identity_sides_stable("LOU", "SMU", "SMU", "Louisville") is False


def test_vlm_home_away_names_respects_home_left():
    home, away = vlm_home_away_names({"home_left": False, "left_team": "OU", "right_team": "LOU"})
    assert home == "LOU" and away == "OU"


def test_auditor_sees_confirm_ticket():
    """Society auditor is gone; confirm ticket still lives on the packet/situation."""
    from qoresence.agents.society.types import AgentPacket

    pkt = AgentPacket(
        score_vlm_locked=True,
        confirm_ticket_id="12cedafeb53420f2",
        situation={"home_score": 14, "away_score": 7, "confirm_ticket_id": "12cedafeb53420f2"},
        health={"video": {"has_frame": True, "age_s": 0.1}},
        phrase="SPRINT",
    )
    assert pkt.score_vlm_locked is True
    assert pkt.confirm_ticket_id == "12cedafeb53420f2"
    assert pkt.situation["confirm_ticket_id"] == "12cedafeb53420f2"
    assert pkt.phrase == "SPRINT"
