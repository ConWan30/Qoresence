"""Locked scorebug sides must not invert when home_left flickers.

Loads modules by file path so this VM does not import qoresence.agents
(cv2/hid/websockets) or qoresence.vision package init.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_cfb = _load("qoresence_profiles_cfb27_product", ROOT / "qoresence/profiles/cfb27_product.py")
identity_compatible = _cfb.identity_compatible
identity_sides_stable = _cfb.identity_sides_stable


def _situation_model():
    vc = _load(
        "qoresence.vision.visual_context",
        ROOT / "qoresence/vision/visual_context.py",
    )
    vision_pkg = types.ModuleType("qoresence.vision")
    vision_pkg.visual_context = vc
    sys.modules.setdefault("qoresence.vision", vision_pkg)
    sys.modules["qoresence.vision.visual_context"] = vc

    types_mod = _load("qoresence.core.types", ROOT / "qoresence/core/types.py")
    core_pkg = sys.modules.get("qoresence.core")
    if core_pkg is None:
        core_pkg = types.ModuleType("qoresence.core")
        sys.modules["qoresence.core"] = core_pkg
    core_pkg.BaseEvent = types_mod.BaseEvent
    core_pkg.EventType = types_mod.EventType
    core_pkg.SourceLobe = types_mod.SourceLobe

    return _load(
        "qoresence_agents_situation_model",
        ROOT / "qoresence/agents/situation_model.py",
    ), types_mod, vc


def test_locked_pair_does_not_swap_sides_on_home_left_flicker():
    assert identity_compatible("KC", "PHI", "Eagles", "Chiefs", profile="madden_27") is True
    assert identity_sides_stable("KC", "PHI", "Chiefs", "Eagles", profile="madden_27") is True
    assert identity_sides_stable("KC", "PHI", "Eagles", "Chiefs", profile="madden_27") is False
    assert identity_sides_stable("KC", "PHI", None, None, profile="madden_27") is True
    assert identity_sides_stable("LOU", "SMU", "SMU", "Louisville") is False


def test_situation_model_holds_locked_sides_when_home_left_flickers():
    sm_mod, types_mod, vc = _situation_model()
    sm = sm_mod.SituationModel()

    def ev(payload: dict):
        return types_mod.BaseEvent(
            session_id="t",
            clock_ns=0,
            source_lobe=types_mod.SourceLobe.VISUAL,
            type=types_mod.EventType.VISUAL_CONTEXT,
            payload=payload,
        )

    sm.update(
        ev(
            {
                "game_category": "football",
                "game_profile": "madden_27",
                "game_state": "gameplay",
                "home_score": 14,
                "away_score": 7,
                "home_team": "KC",
                "away_team": "PHI",
                "home_left": False,
                "score_vlm_locked": True,
                "confirm_ticket_id": "cafecafecafecafe",
            }
        )
    )
    assert (sm.state.home_team, sm.state.away_team) == ("KC", "PHI")
    assert sm.state.home_left is False

    sm.update(
        ev(
            {
                "game_category": "football",
                "game_profile": "madden_27",
                "game_state": "gameplay",
                "home_score": 14,
                "away_score": 7,
                "home_team": "PHI",
                "away_team": "KC",
                "home_left": True,
                "score_vlm_locked": True,
                "confirm_ticket_id": "cafecafecafecafe",
            }
        )
    )
    assert (sm.state.home_team, sm.state.away_team) == ("KC", "PHI")
    assert sm.state.home_left is False
    assert (sm.state.home_score, sm.state.away_score) == (14, 7)
    assert sm.to_dict()["home_left"] is False
    assert vc is not None
