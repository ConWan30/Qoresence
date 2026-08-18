"""Operator profile pin survives NCAA auto-detect."""

from __future__ import annotations

from pathlib import Path

from qoresence.agents.situation_model import SituationModel
from qoresence.core.operator_profile import (
    load_last_profile,
    resolve_operator_profile,
    save_last_profile,
)
from qoresence.core.types import BaseEvent, EventType, SourceLobe


def test_resolve_cli_pins(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QORESENCE_LAST_PROFILE_PATH", str(tmp_path / "last"))
    monkeypatch.delenv("QORESENCE_GAME_PROFILE", raising=False)
    pid, pinned = resolve_operator_profile("madden")
    assert pid == "madden_27"
    assert pinned is True


def test_resolve_last_session_pins(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QORESENCE_LAST_PROFILE_PATH", str(tmp_path / "last"))
    monkeypatch.delenv("QORESENCE_GAME_PROFILE", raising=False)
    save_last_profile("madden_27")
    assert load_last_profile() == "madden_27"
    pid, pinned = resolve_operator_profile(None)
    assert pid == "madden_27"
    assert pinned is True


def test_first_run_ncaa_is_not_a_pin(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QORESENCE_LAST_PROFILE_PATH", str(tmp_path / "missing"))
    monkeypatch.delenv("QORESENCE_GAME_PROFILE", raising=False)
    pid, pinned = resolve_operator_profile(None)
    assert pid == "ncaa_football_27"
    assert pinned is False


def test_situation_pin_rejects_ncaa_claim():
    sit = SituationModel()
    sit.seed_profile("madden_27", pinned=True)
    ev = BaseEvent(
        session_id="s",
        clock_ns=1,
        source_lobe=SourceLobe.FUSION,
        type=EventType.GAME_DETECTED,
        payload={"profile_id": "ncaa_football_27"},
    )
    sit.update(ev)
    assert sit.state.game_profile == "madden_27"
    ev2 = BaseEvent(
        session_id="s",
        clock_ns=2,
        source_lobe=SourceLobe.FUSION,
        type=EventType.TITLE_PRESENCE,
        payload={"claim": True, "profile_id": "ncaa_football_27", "hysteresis_state": "locked"},
    )
    sit.update(ev2)
    assert sit.state.game_profile == "madden_27"
    assert sit.state.title_hysteresis == "locked"
