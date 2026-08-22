"""Agent Companion — auto-clip duty stays on. Observation only."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_COMP = Path(__file__).resolve().parents[1] / "qoresence" / "agents" / "companion.py"
_spec = importlib.util.spec_from_file_location("qoresence_agents_companion", _COMP)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
build_companion = _mod.build_companion
clip_armed = _mod.clip_armed


def test_auto_clip_duty_always_on():
    pack = build_companion()
    assert pack["auto_clip"] is True
    assert pack["clip"]["duty"] == "auto"
    assert pack["plane"] == "qoresence-observation"
    assert pack["claim_ceiling"] == "observation_only"
    assert any("auto-clips clutch" in s for s in pack["may_say"])


def test_clip_armed_matches_fast_gates():
    assert clip_armed(coupling=0.72, red=True, close=False, late=False, climax=0.1) is True
    assert clip_armed(coupling=0.72, red=False, close=True, late=True, climax=0.1) is True
    assert clip_armed(coupling=0.40, red=True, close=False, late=False, climax=0.1) is False
    assert clip_armed(coupling=0.20, red=False, close=False, late=False, climax=0.70) is True


def test_close_gate_requires_locked_board():
    unlocked = build_companion(
        situation={"home_score": 21, "away_score": 20, "quarter": 4},
        coupling={"coupling": 0.8},
    )
    assert unlocked["clip"]["gates"]["close"] is False
    assert unlocked["clip"]["armed"] is False
    assert "score_not_locked" in unlocked["must_not_invent"]

    locked = build_companion(
        situation={
            "home_score": 21,
            "away_score": 20,
            "quarter": 4,
            "score_vlm_locked": True,
        },
        coupling={"coupling": 0.8},
    )
    assert locked["clip"]["gates"]["close"] is True
    assert locked["clip"]["gates"]["late"] is True
    assert locked["clip"]["armed"] is True


def test_last_clip_and_society_roles():
    pack = build_companion(
        moments=[
            {
                "title": "FAST HDMI CLIP 8s",
                "action": "clip",
                "moment_path": "fast",
                "name": "hdmi_clip_x.mp4",
                "url": "/media/clips/hdmi_clip_x.mp4",
            }
        ],
        society={
            "enabled": True,
            "alive": True,
            "last": [
                {"role": "drive_coach", "action": "note", "text": "Drive phase red_zone."},
                {
                    "role": "ghost_editor",
                    "action": "propose_cut",
                    "text": "propose_cut hdmi_clip_x.mp4 4.0-22.0s · TOUCHDOWN",
                    "refs": {
                        "clip": "hdmi_clip_x.mp4",
                        "t_s_in": 4.0,
                        "t_s_out": 22.0,
                        "title": "TOUCHDOWN",
                    },
                },
            ],
        },
        drive_graph={"phase": "red_zone", "climax": {"score": 0.81, "best_label": "score_play"}},
    )
    assert pack["clip"]["last"]["path"] == "fast"
    assert pack["coach"]["text"] == "Drive phase red_zone."
    assert pack["cut"]["title"] == "TOUCHDOWN"
    assert pack["cut"]["t_s_in"] == 4.0
    assert pack["drive"]["climax"] == 0.81


def test_does_not_invent_unlocked_score_in_may_say():
    pack = build_companion(
        situation={"home_score": 14, "away_score": 7},
        why_last={"line": "14-7 late drive", "climax_score": 0.2},
    )
    joined = " ".join(pack["may_say"])
    assert "14-7" not in joined
    assert "the scoreboard" in joined
