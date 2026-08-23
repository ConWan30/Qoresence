"""Agent Society — default OFF, leftover stub, no personality roles."""

from __future__ import annotations

from qoresence.agents.society.config import AgentSocietyConfig
from qoresence.agents.society.policy import SocietyPolicy
from qoresence.agents.society.runtime import SocietyRuntime
from qoresence.agents.society.types import AgentPacket, AgentReceipt
from qoresence.core.unified_config import RetinaUnifiedConfig


def test_play_leaves_society_off():
    from argparse import Namespace

    from qoresence.cli import apply_society_cli

    cfg = RetinaUnifiedConfig(session_id="s", session_head_ns=1)
    assert getattr(cfg.society, "enabled", True) is False
    play = apply_society_cli(
        cfg,
        Namespace(play=True, agent_society=False, agent_society_roles=None, no_agent_society=False),
    )
    assert play.society.enabled is False


def test_agent_society_flag_enables_stub_without_personalities():
    from argparse import Namespace

    from qoresence.cli import apply_society_cli

    cfg = RetinaUnifiedConfig(session_id="s", session_head_ns=1)
    on = apply_society_cli(
        cfg,
        Namespace(play=True, agent_society=True, agent_society_roles=None, no_agent_society=False),
    )
    assert on.society.enabled is True
    assert on.society.roles == ()
    off = apply_society_cli(
        cfg,
        Namespace(play=True, no_agent_society=True, agent_society=True, agent_society_roles=None),
    )
    assert off.society.enabled is False


def test_resolve_key_file_falls_back_to_clutchbot(tmp_path, monkeypatch):
    from qoresence.agents.society.config import resolve_key_file
    from qoresence.agents.society.quicksilver import SocietyQuicksilver

    clutch = tmp_path / "quicksilver_clutchbot.key"
    clutch.write_text("test-society-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QORESENCE_SOCIETY_KEY_FILE", raising=False)
    monkeypatch.delenv("QORESENCE_QUICKSILVER_KEY_FILE", raising=False)
    monkeypatch.delenv("QUICKSILVER_API_KEY", raising=False)
    monkeypatch.delenv("QUICKSILVERPRO_API_KEY", raising=False)
    monkeypatch.delenv("QORESENCE_QUICKSILVER_API_KEY", raising=False)
    (tmp_path / ".secrets").mkdir()
    (tmp_path / ".secrets" / "quicksilver_clutchbot.key").write_text(
        "test-society-key\n", encoding="utf-8"
    )
    assert resolve_key_file(".secrets/quicksilver.key").endswith("quicksilver_clutchbot.key")
    qs = SocietyQuicksilver(AgentSocietyConfig(api_key_file=".secrets/quicksilver.key"))
    assert qs.available() is True


def test_society_config_default_off():
    cfg = AgentSocietyConfig()
    assert cfg.enabled is False
    assert cfg.roles == ()
    assert cfg.model_reason == "nemotron-3.5-lightning"
    assert cfg.model_scene == "gemini-3.5-flash-lite"
    env = AgentSocietyConfig.from_env()
    assert env.roles == ()


def test_unified_config_society_off():
    cfg = RetinaUnifiedConfig(session_id="s", session_head_ns=1)
    soc = cfg.society
    assert soc is not None
    assert getattr(soc, "enabled", True) is False


def test_policy_strips_digits_unless_locked():
    pol = SocietyPolicy(cooldown_s=0)
    pkt = AgentPacket(situation={"home_score": 14, "away_score": 13}, score_vlm_locked=False)
    rec = AgentReceipt(role="leftover", action="note", text="They go 14-13 late")
    out = pol.finalize(rec, pkt)
    assert "14-13" not in out.text
    pkt.score_vlm_locked = True
    pkt.confirm_ticket_id = "abcdabcdabcdabcd"
    pkt.situation["confirm_ticket_id"] = "abcdabcdabcdabcd"
    rec2 = AgentReceipt(role="leftover", action="note", text="Board 14-13 holds")
    out2 = pol.finalize(rec2, pkt)
    assert "14-13" in out2.text


def test_policy_unknown_role_ignored():
    pol = SocietyPolicy()
    assert pol.allow_role("not_a_role", ("spam_warden",)) is False
    assert pol.allow_role("spam_warden", ("spam_warden",)) is False


def test_receipt_round_trip():
    r = AgentReceipt(role="stub", action="audit", text="ok", refs={"n": 1}, ts_ns=3)
    d = r.to_dict()
    assert d["role"] == "stub"
    assert d["action"] == "audit"
    assert d["refs"]["n"] == 1


def test_opt_in_tick_without_roles_is_noop():
    rt = SocietyRuntime(
        AgentSocietyConfig(enabled=True, roles=(), api_key_file="no/such.key", cooldown_s=0)
    )
    recs = rt.tick(AgentPacket(last_commits=[{"message": "heat", "path": "fast", "clock_ns": 1}]))
    assert recs == []


def test_frozen_personality_roles_are_gone():
    """Phase 5: personality / duplicate Sync Warden modules must not exist."""
    import importlib

    import pytest

    gone = (
        "drive_coach",
        "ghost_editor",
        "prediction_steward",
        "spam_warden",
        "pilot_auditor",
        "sync_warden",
    )
    for name in gone:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(f"qoresence.agents.society.roles.{name}")


def test_society_stub_imports_and_tick_is_noop():
    """Leftover society package must import; opt-in tick must not crash."""
    from qoresence.agents.society import SocietyRuntime as RT
    from qoresence.agents.society import start_society

    cfg = AgentSocietyConfig(enabled=True, roles=(), cooldown_s=0)
    assert start_society(AgentSocietyConfig(enabled=False)) is None
    recs = RT(cfg).tick(AgentPacket(), roles=())
    assert recs == []
