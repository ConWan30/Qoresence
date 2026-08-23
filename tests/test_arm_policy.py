"""Phase 3 Arm policy — climax, locked score delta, or operator POST."""

from __future__ import annotations

from qoresence.agents.actuators import arm_allowed, stem_suggest


def test_arm_allowed_climax():
    assert arm_allowed(climax=0.65, locked_score_delta=False, operator_post=False) is True
    assert arm_allowed(climax=0.64, locked_score_delta=False, operator_post=False) is False


def test_arm_allowed_locked_score_delta():
    assert arm_allowed(climax=0.0, locked_score_delta=True, operator_post=False) is True


def test_arm_allowed_operator_post():
    assert arm_allowed(climax=0.0, locked_score_delta=False, operator_post=True) is True


def test_arm_refuses_coupling_red_alone():
    """Phase 3 dropped coupling+red as an Arm license."""
    assert arm_allowed(climax=0.2, locked_score_delta=False, operator_post=False) is False


def test_stem_suggest_never_sets_conductor_mode():
    assert stem_suggest(climax=0.9, locked_score_delta=False, operator_post=False) == "armed"
    assert stem_suggest(climax=0.1, locked_score_delta=False, operator_post=False) is None


def test_conductor_payload_keeps_authority_mode(monkeypatch):
    from qoresence.stem.conductor import DirectorBrief

    brief = DirectorBrief(mode="watch", why="watching", arm_hot=False, suggested="armed")
    payload = brief.to_payload()
    assert payload["mode"] == "watch"
    assert payload["suggested"] == "armed"
    assert payload["mode"] != payload["suggested"]
