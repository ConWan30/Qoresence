"""Agent Society — default OFF, policy, rules-only roles."""

from __future__ import annotations

from qoresence.agents.society.config import AgentSocietyConfig
from qoresence.agents.society.policy import SocietyPolicy
from qoresence.agents.society.roles.spam_warden import run as warden_run
from qoresence.agents.society.runtime import SocietyRuntime
from qoresence.agents.society.types import AgentPacket, AgentReceipt
from qoresence.core.unified_config import RetinaUnifiedConfig


def test_play_enables_society_all_roles():
    from argparse import Namespace

    from qoresence.cli import apply_society_cli

    cfg = RetinaUnifiedConfig(session_id="s", session_head_ns=1)
    assert getattr(cfg.society, "enabled", True) is False
    on = apply_society_cli(cfg, Namespace(play=True, agent_society=False, agent_society_roles=None, no_agent_society=False))
    assert on.society.enabled is True
    assert set(on.society.roles) >= {
        "spam_warden",
        "pilot_auditor",
        "drive_coach",
        "ghost_editor",
        "prediction_steward",
    }
    off = apply_society_cli(cfg, Namespace(play=True, no_agent_society=True, agent_society=False, agent_society_roles=None))
    assert off.society.enabled is False


def test_society_config_default_off():
    cfg = AgentSocietyConfig()
    assert cfg.enabled is False
    assert "spam_warden" in cfg.roles
    env = AgentSocietyConfig.from_env()
    # env may be on if operator exported the flag; still valid roles
    assert all(r in {"spam_warden", "pilot_auditor", "drive_coach", "ghost_editor", "prediction_steward"} for r in env.roles)


def test_unified_config_society_off():
    cfg = RetinaUnifiedConfig(session_id="s", session_head_ns=1)
    soc = cfg.society
    assert soc is not None
    assert getattr(soc, "enabled", True) is False


def test_policy_strips_digits_unless_locked():
    pol = SocietyPolicy(cooldown_s=0)
    pkt = AgentPacket(situation={"home_score": 14, "away_score": 13}, score_vlm_locked=False)
    rec = AgentReceipt(role="drive_coach", action="note", text="They go 14-13 late")
    out = pol.finalize(rec, pkt)
    assert "14-13" not in out.text
    pkt.score_vlm_locked = True
    rec2 = AgentReceipt(role="drive_coach", action="note", text="Board 14-13 holds")
    out2 = pol.finalize(rec2, pkt)
    assert "14-13" in out2.text


def test_policy_unknown_role_ignored():
    pol = SocietyPolicy()
    assert pol.allow_role("not_a_role", ("spam_warden",)) is False
    assert pol.allow_role("spam_warden", ("spam_warden",)) is True


def test_receipt_round_trip():
    r = AgentReceipt(role="pilot_auditor", action="audit", text="ok", refs={"n": 1}, ts_ns=3)
    d = r.to_dict()
    assert d["role"] == "pilot_auditor"
    assert d["action"] == "audit"
    assert d["refs"]["n"] == 1


def test_rules_only_no_key():
    rt = SocietyRuntime(
        AgentSocietyConfig(enabled=True, roles=("spam_warden",), api_key_file="no/such.key", cooldown_s=0)
    )
    assert rt.qs.available() is False
    recs = rt.tick(
        AgentPacket(last_commits=[{"message": "heat", "path": "fast", "clock_ns": 1}]),
        roles=("spam_warden",),
    )
    assert recs
    assert recs[0].action == "allow"
    assert recs[0].model == "rules"


def test_spam_warden_vetoes_fast_digits():
    rec = warden_run(
        AgentPacket(
            path="fast",
            last_commits=[{"message": "Score 21-14 boom", "path": "fast", "clock_ns": 9}],
        )
    )
    assert rec is not None
    assert rec.action == "veto"


def test_spam_warden_vetoes_near_duplicate():
    rec = warden_run(
        AgentPacket(
            clock_ns=50,
            last_commits=[
                {"message": "Live football", "path": "confirm", "clock_ns": 10},
                {"message": "Live football", "path": "confirm", "clock_ns": 40},
            ],
        )
    )
    assert rec is not None
    assert rec.action == "veto"


def test_ghost_editor_proposes_window():
    from qoresence.agents.society.roles.ghost_editor import run as ed

    rec = ed(
        AgentPacket(
            clip_hits=[
                {
                    "name": "hdmi_clip_x.mp4",
                    "chapter": {"t_s": 10.0, "label": "TOUCHDOWN"},
                    "onset_count": 3,
                }
            ]
        )
    )
    assert rec is not None
    assert rec.action == "propose_cut"
    assert rec.refs["t_s_in"] == 4.0
    assert rec.refs["t_s_out"] == 22.0
