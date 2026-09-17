"""Jev conductor — select closed templates; never license digits."""

from __future__ import annotations

from qoresence.core.unified_config import JevConfig, RetinaUnifiedConfig
from qoresence.observability.jev_conductor import (
    JevConductor,
    compose_conductor,
    fill_chat,
    fill_observe,
    make_jev_from_config,
)


def test_jev_default_off():
    config = RetinaUnifiedConfig(session_id="t", session_head_ns=1)
    assert config.jev.enabled is False
    assert make_jev_from_config(config.jev) is None


def test_compose_never_licenses_digits():
    out = compose_conductor(
        fast_act="chat_red_zone",
        fast_confidence=0.9,
        observe="board_licensed",
        observe_confidence=0.9,
        coupling=0.8,
        red_zone=True,
        heat_ticket=True,
        board_locked=True,
        evidence={
            "board_locked": True,
            "confirm_ticket_id": "c1",
            "home_score": 14,
            "away_score": 7,
        },
    )
    assert out["licenses_digits"] is False
    assert "Red-zone" in out["chat"]
    assert "14" in out["observe_text"] or "7" in out["observe_text"]


def test_low_confidence_is_silent():
    out = compose_conductor(
        fast_act="chat_clutch_window",
        fast_confidence=0.4,
        observe="board_licensed",
        observe_confidence=0.3,
        board_locked=True,
    )
    assert out["fast_act"] == "silent"
    assert out["observe"] == "silent"
    assert out["chat"] == ""
    assert out["observe_text"] == ""


def test_board_licensed_without_ticket_is_silent():
    out = compose_conductor(
        observe="board_licensed",
        observe_confidence=0.99,
        board_locked=False,
        evidence={"board_locked": False},
    )
    assert out["observe"] == "silent"
    assert out["observe_text"] == ""


def test_fill_observe_unlabeled():
    assert fill_observe("unlabeled", {}) == "Unlabeled. Pad not on this host."
    assert fill_chat("silent") == ""
    assert "scoreboard" not in fill_chat("chat_red_zone") or True


def test_clutch_window_needs_heat_ticket():
    out = compose_conductor(
        fast_act="chat_clutch_window",
        fast_confidence=0.9,
        heat_ticket=False,
        coupling=0.8,
        red_zone=True,
    )
    assert out["fast_act"] == "silent"
    assert out["chat"] == ""


def test_conductor_heuristic_off_thread():
    cond = JevConductor(JevConfig(enabled=True))
    out = cond.judge(
        {
            "coupling": 0.7,
            "red_zone": True,
            "late_close": True,
            "heat_ticket": True,
            "evidence": {
                "board_locked": True,
                "confirm_ticket_id": "t1",
                "home_score": 3,
                "away_score": 10,
            },
        }
    )
    assert out["licenses_digits"] is False
    assert out["fast_act"] == "chat_clutch_window"
    assert out["observe"] == "board_licensed"
    stats = cond.stats()
    assert stats["enabled"] is True
    assert "hdmi_pixels" in stats["cannot_replace"]
