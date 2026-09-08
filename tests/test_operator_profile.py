"""Operator profile pin survives NCAA auto-detect."""

from __future__ import annotations

from pathlib import Path

from qoresence.agents.situation_model import SituationModel
from qoresence.core.operator_profile import (
    load_last_profile,
    operator_pin_blocks_switch,
    persist_operator_pin,
    resolve_operator_profile,
    save_last_profile,
)
from qoresence.core.types import BaseEvent, EventType, SourceLobe
from qoresence.core.unified_config import GameProfileId


def test_resolve_cli_pins(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QORESENCE_LAST_PROFILE_PATH", str(tmp_path / "last"))
    monkeypatch.delenv("QORESENCE_GAME_PROFILE", raising=False)
    pid, pinned = resolve_operator_profile("madden")
    assert pid == "madden_27"
    assert pinned is True


def test_resolve_env_pins(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QORESENCE_LAST_PROFILE_PATH", str(tmp_path / "last"))
    monkeypatch.setenv("QORESENCE_GAME_PROFILE", "madden")
    pid, pinned = resolve_operator_profile(None)
    assert pid == "madden_27"
    assert pinned is True


def test_cli_overrides_env_pin(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QORESENCE_LAST_PROFILE_PATH", str(tmp_path / "last"))
    monkeypatch.setenv("QORESENCE_GAME_PROFILE", "ncaa_football_27")
    pid, pinned = resolve_operator_profile("madden_27")
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


def test_unpinned_fallback_does_not_persist(tmp_path: Path, monkeypatch):
    last = tmp_path / "last"
    monkeypatch.setenv("QORESENCE_LAST_PROFILE_PATH", str(last))
    monkeypatch.delenv("QORESENCE_GAME_PROFILE", raising=False)
    pid, pinned = resolve_operator_profile(None)
    persist_operator_pin(pid, pinned=pinned)
    assert pinned is False
    assert not last.exists()
    assert load_last_profile() is None
    # Safety net must not treat a missing last-file as a pin.
    assert operator_pin_blocks_switch(pid, "madden_27", pinned=False) is False


def test_pinned_persists_last_profile(tmp_path: Path, monkeypatch):
    last = tmp_path / "last"
    monkeypatch.setenv("QORESENCE_LAST_PROFILE_PATH", str(last))
    monkeypatch.delenv("QORESENCE_GAME_PROFILE", raising=False)
    persist_operator_pin("madden_27", pinned=True)
    assert load_last_profile() == "madden_27"
    persist_operator_pin("ncaa_football_27", pinned=False)
    # Unpinned write is a no-op — must not clobber a real pin.
    assert load_last_profile() == "madden_27"


def test_operator_pin_blocks_optical_switch(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QORESENCE_LAST_PROFILE_PATH", str(tmp_path / "missing"))
    monkeypatch.delenv("QORESENCE_GAME_PROFILE", raising=False)
    assert (
        operator_pin_blocks_switch("madden_27", GameProfileId.NCAA_FOOTBALL_27, pinned=True)
        is True
    )
    assert operator_pin_blocks_switch("madden_27", "madden_27", pinned=True) is False
    assert operator_pin_blocks_switch("madden_27", "ncaa_football_27", pinned=False) is False


def test_last_file_safety_net_blocks_when_flag_dropped(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QORESENCE_LAST_PROFILE_PATH", str(tmp_path / "last"))
    monkeypatch.delenv("QORESENCE_GAME_PROFILE", raising=False)
    persist_operator_pin("madden_27", pinned=True)
    # Config flag lost, but last file still matches the operator profile.
    assert operator_pin_blocks_switch("madden_27", "ncaa_football_27", pinned=False) is True


def test_situation_pin_rejects_ncaa_claim_without_locked_title():
    """Unlocked GAME_DETECTED ncaa claim does not yank a pinned madden profile."""
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
    assert sit.state.game_profile == "cfb_27"
    assert sit.state.title_hysteresis == "locked"
    assert sit.state.title_claim is True


def test_visual_context_does_not_yank_pin():
    sit = SituationModel()
    sit.seed_profile("madden_27", pinned=True)
    ev = BaseEvent(
        session_id="s",
        clock_ns=1,
        source_lobe=SourceLobe.VISUAL,
        type=EventType.VISUAL_CONTEXT,
        payload={
            "game_title": "College Football 27",
            "game_profile": "ncaa_football_27",
            "game_category": "football",
            "game_state": "gameplay",
            "confidence": 0.9,
        },
    )
    sit.update(ev)
    assert sit.state.game_profile == "cfb_27"
    assert sit.state.game_title == "College Football 27"


def test_unpinned_optical_lock_may_adopt_title():
    sit = SituationModel()
    sit.seed_profile("ncaa_football_27", pinned=False)
    ev = BaseEvent(
        session_id="s",
        clock_ns=1,
        source_lobe=SourceLobe.FUSION,
        type=EventType.GAME_DETECTED,
        payload={"profile_id": "madden_27", "plane": "qoresence-observation"},
    )
    sit.update(ev)
    assert sit.state.game_profile == "madden_27"

