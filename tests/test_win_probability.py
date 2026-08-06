"""Unit tests for FootballWinProbability + EP helpers."""
from __future__ import annotations

import math
import pytest

from qoresence.agents.win_probability import (
    FOOTBALL_EP_TABLE,
    FootballWinProbability,
    _ep_for_yards,
    _sigmoid,
    parse_field_position,
)

# ---------------------------------------------------------------------------
# parse_field_position
# ---------------------------------------------------------------------------
class TestParseFieldPosition:
    def test_none_and_empty(self):
        assert parse_field_position(None) is None
        assert parse_field_position("") is None
        assert parse_field_position("   ") is None

    def test_midfield_variants(self):
        assert parse_field_position("midfield") == 50
        assert parse_field_position("50") == 50
        assert parse_field_position("mid") == 50
        assert parse_field_position("  MIDFIELD  ") == 50

    def test_opp(self):
        assert parse_field_position("opp 10") == 10
        assert parse_field_position("opponent 15") == 15
        assert parse_field_position("OPP 35") == 35
        assert parse_field_position("opp10") == 10  # no space still matches

    def test_own(self):
        assert parse_field_position("own 45") == 55  # 100-45
        assert parse_field_position("own 20") == 80
        assert parse_field_position("own 1") == 99  # clamped
        assert parse_field_position("own 99") == 1
        assert parse_field_position("Own 45 ") == 55

    def test_bare_number(self):
        assert parse_field_position("30") == 30
        assert parse_field_position("  99 ") == 99

    def test_clamping(self):
        assert parse_field_position("opp 0") == 1
        assert parse_field_position("opp 150") == 99

    def test_case_insensitive_and_whitespace(self):
        assert parse_field_position("  OPPONENT  22  ") == 22
        assert parse_field_position(" OwN 10 ") == 90


class TestEP:
    def test_none_returns_zero(self):
        assert _ep_for_yards(None) == 0.0

    def test_exact_hit(self):
        for yds, ep in FOOTBALL_EP_TABLE.items():
            assert _ep_for_yards(yds) == pytest.approx(ep)

    def test_interpolation(self):
        # 45 is halfway between 40->3.0 and 50->2.2 => 2.6
        assert _ep_for_yards(45) == pytest.approx(2.6, abs=0.05)
        # 75 between 70->1.2 and 80->0.5 => 0.85
        assert _ep_for_yards(75) == pytest.approx(0.85, abs=0.1)

    def test_clamp(self):
        assert _ep_for_yards(1) == FOOTBALL_EP_TABLE[1]
        assert _ep_for_yards(0) == FOOTBALL_EP_TABLE[1]  # clamped to 1
        assert _ep_for_yards(150) == FOOTBALL_EP_TABLE[99]
        assert _ep_for_yards(99) == FOOTBALL_EP_TABLE[99]


class TestSigmoid:
    def test_mid(self):
        assert _sigmoid(0) == pytest.approx(0.5)

    def test_extremes(self):
        assert _sigmoid(100) == 1.0
        assert _sigmoid(-100) == 0.0
        assert _sigmoid(30) == 1.0  # clamped
        assert _sigmoid(-30) == 0.0


class TestFootballWinProbability:
    def _base_state(self, **overrides):
        d = dict(
            quarter=1,
            clock_seconds=900,
            down=1,
            yards_to_go=10,
            field_position="own 25",  # yds_to_opp 75
            score_diff=0,
        )
        d.update(overrides)
        return d

    def test_compute_keys_and_clamp(self):
        wp = FootballWinProbability()
        r = wp.compute(self._base_state())
        for k in ("win_prob", "expected_points", "wp_swing", "yds_to_opp", "score_diff", "is_ot"):
            assert k in r
        assert 0.01 <= r["win_prob"] <= 0.99

    def test_wp_swing_first_zero_then_delta(self):
        wp = FootballWinProbability()
        r1 = wp.compute(self._base_state(score_diff=0))
        assert r1["wp_swing"] == 0.0
        r2 = wp.compute(self._base_state(score_diff=7))
        assert r2["wp_swing"] == pytest.approx(r2["win_prob"] - r1["win_prob"])
        assert r2["wp_swing"] > 0

    def test_reset_clears_swing(self):
        wp = FootballWinProbability()
        wp.compute(self._base_state(score_diff=7))
        wp.reset()
        r = wp.compute(self._base_state(score_diff=0))
        assert r["wp_swing"] == 0.0

    def test_leading_increases_wp(self):
        wp = FootballWinProbability()
        r_trail = FootballWinProbability().compute(self._base_state(score_diff=-14))
        r_lead = FootballWinProbability().compute(self._base_state(score_diff=14))
        assert r_lead["win_prob"] > r_trail["win_prob"]
        assert r_lead["win_prob"] > 0.6
        assert r_trail["win_prob"] < 0.4

    def test_ot_dominated_by_score(self):
        wp_ot = FootballWinProbability()
        r = wp_ot.compute(self._base_state(quarter=5, clock_seconds=0, score_diff=3, field_position="opp 10"))
        assert r["is_ot"] is True
        assert r["win_prob"] > 0.7  # OT + FG lead + redzone should be favored
        # trailing in OT should be worse than tied
        r_trail = FootballWinProbability().compute(self._base_state(quarter=5, clock_seconds=0, score_diff=-3))
        assert r["win_prob"] > r_trail["win_prob"]

    def test_down_distance_adjusts_ep(self):
        wp = FootballWinProbability()
        r_easy = wp.compute(self._base_state(down=1, yards_to_go=10, field_position="own 40"))
        # 3rd & 10 should lower EP vs 1st & 10
        r_hard = FootballWinProbability().compute(self._base_state(down=3, yards_to_go=10, field_position="own 40"))
        assert r_hard["expected_points"] < r_easy["expected_points"]
        # 4th down even lower
        r_4th = FootballWinProbability().compute(self._base_state(down=4, yards_to_go=1, field_position="opp 30"))
        r_1st = FootballWinProbability().compute(self._base_state(down=1, yards_to_go=10, field_position="opp 30"))
        assert r_4th["expected_points"] < r_1st["expected_points"]

    def test_late_game_score_matters_more(self):
        # 14-pt lead early vs late: late should be higher WP
        wp_early = FootballWinProbability().compute(dict(quarter=1, clock_seconds=900, score_diff=14, field_position="midfield"))
        wp_late = FootballWinProbability().compute(dict(quarter=4, clock_seconds=120, score_diff=14, field_position="midfield"))
        assert wp_late["win_prob"] > wp_early["win_prob"]

    def test_end_of_half_dampening(self):
        # Q2 <120s and close game should slightly reduce score impact (more total_remaining dampening)
        # We test that code path doesn't crash and produces valid WP
        wp = FootballWinProbability()
        r = wp.compute(dict(quarter=2, clock_seconds=60, score_diff=7, field_position="opp 20"))
        assert 0.01 <= r["win_prob"] <= 0.99

    def test_coerce_alternate_keys(self):
        wp = FootballWinProbability()
        # home/away + possession
        r = wp.compute(dict(home_score=21, away_score=14, possession="home", quarter=3, clock_seconds=600))
        assert r["score_diff"] == 7
        r2 = wp.compute(dict(home_score=21, away_score=14, possession="away", quarter=3, clock_seconds=600))
        assert r2["score_diff"] == -7

    def test_five_scenarios_from_bench(self):
        """Mirror eval/wp_bench deterministic scenarios."""
        scenarios = [
            {"quarter": 1, "clock_seconds": 900, "score_diff": 0, "field_position": "own 25"},  # blowout early neutral
            {"quarter": 4, "clock_seconds": 90, "score_diff": 3, "field_position": "opp 8"},  # close late redzone
            {"quarter": 5, "clock_seconds": 0, "score_diff": 0, "field_position": "opp 25"},  # OT
            {"quarter": 2, "clock_seconds": 30, "score_diff": 7, "field_position": "midfield"},  # end-half
            {"quarter": 4, "clock_seconds": 20, "score_diff": -3, "field_position": "opp 2"},  # 4th & inches goal line
        ]
        for s in scenarios:
            r = FootballWinProbability().compute(s)
            assert 0.01 <= r["win_prob"] <= 0.99
            assert "wp_swing" in r

    def test_calibrate_noop(self):
        wp = FootballWinProbability()
        wp.calibrate([{"label": 1}])  # should not raise
        wp.calibrate(None)

    def test_coerce_from_object(self):
        class Obj:
            quarter = 4
            clock_seconds = 300
            score_diff = 7
            field_position = "opp 10"
            home_score = None
            away_score = None
            possession = None
            down = 1
            yards_to_go = 10
        wp = FootballWinProbability()
        r = wp.compute(Obj())
        assert 0.01 <= r["win_prob"] <= 0.99
