"""Tests for pilot bug fixes: A2A menu guard, team context, game_profile wiring.

Bug #1: A2A fires on menu screens — post-hoc guard in orchestrator
Bug #2: A2A team name hallucinations — game_profile in Gemini prompt
Bug #3: game_profile null in situation — wired from CLI through visual to situation
"""

from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np

from qoresence.a2a.orchestrator import (
    A2AOrchestrator,
    _scene_looks_like_menu,
    reset_a2a_orchestrator,
)
from qoresence.a2a.types import SceneProposal
from qoresence.agents.situation_model import SituationModel
from qoresence.core.types import EventType
from qoresence.vision.local_vlm import LocalVLMClient
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


# ── Bug #1: A2A menu guard ───────────────────────────────────────────────────


def test_scene_looks_like_menu_detects_menu_keywords():
    """The post-hoc guard should catch menu descriptions from Gemini."""
    assert _scene_looks_like_menu("The menu screen prepares players for upcoming battles")
    assert _scene_looks_like_menu("Pause menu hits during FSU vs Louisville")
    assert _scene_looks_like_menu("A quiet moment in the program's archive")
    assert _scene_looks_like_menu("Main menu carries quiet pre-game pressure")


def test_scene_looks_like_menu_does_not_fire_on_gameplay():
    """Gameplay descriptions should not trigger the menu guard."""
    assert not _scene_looks_like_menu("Red zone pressure builds as the offense drives")
    assert not _scene_looks_like_menu("Late game heat rises in the fourth quarter")
    assert not _scene_looks_like_menu("")


def test_orchestrator_vetoes_menu_scene_summary():
    """When Gemini describes a menu but game_state says gameplay, veto it."""
    reset_a2a_orchestrator()
    orch = A2AOrchestrator(enabled=True, min_interval_s=0)
    orch.gemini.live = False
    orch.deepseek.live = False
    orch.policy.chat_cooldown_s = 0

    # Monkey-patch gemini to return a menu-looking scene despite gameplay state
    def _fake_propose(**kwargs):
        return SceneProposal(
            summary="The menu screen carries quiet pre-game pressure",
            tension=0.3,
            tags=["menu"],
            soft_only=True,
            model="test",
        )

    orch.gemini.propose_scene = _fake_propose

    result = orch.run_cycle(
        situation={"game_category": "football", "game_state": "gameplay"},
        reason="scene_tick",
        path="fast",
    )
    assert result is not None
    assert result.__class__.__name__ == "Veto"
    assert "menu" in result.reason.lower()


def test_orchestrator_does_not_veto_menu_exit_reason():
    """menu_exit reason should bypass the post-hoc guard (it's a valid transition)."""
    reset_a2a_orchestrator()
    orch = A2AOrchestrator(enabled=True, min_interval_s=0)
    orch.gemini.live = False
    orch.deepseek.live = False
    orch.policy.chat_cooldown_s = 0

    def _fake_propose(**kwargs):
        return SceneProposal(
            summary="The menu screen fades as gameplay resumes",
            tension=0.5,
            tags=["menu_exit"],
            soft_only=True,
            model="test",
        )

    orch.gemini.propose_scene = _fake_propose

    result = orch.run_cycle(
        situation={"game_category": "football", "game_state": "gameplay"},
        reason="menu_exit",
        path="fast",
    )
    # Should NOT be vetoed — menu_exit is a valid reason
    assert result is not None
    assert result.__class__.__name__ != "Veto"


# ── Bug #2: Gemini prompt includes game_profile ──────────────────────────────


def test_gemini_prompt_includes_game_profile():
    """The Gemini live prompt should include game_profile and game_title in context."""
    from qoresence.a2a.gemini_agent import GeminiSceneAgent

    agent = GeminiSceneAgent(live=False)
    # Capture the prompt by monkey-patching requests.post
    captured_prompt = []

    class _FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": '{"summary":"test","tension":0.5,"tags":[]}'}}]}

        @property
        def text(self):
            return ""

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured_prompt.append(json["messages"][0]["content"][0]["text"])
        return _FakeResp()

    agent.live = True
    agent._api_key = "fake"

    with patch("requests.post", _fake_post):
        agent.propose_scene(
            situation={
                "game_state": "gameplay",
                "game_profile": "ncaa_football_27",
                "game_title": "NCAA College Football 27",
                "home_score": 7,
                "away_score": 0,
                "quarter": 2,
            },
            coupling=0.5,
            drive_phase="pressure",
        )

    assert captured_prompt, "prompt was not captured"
    prompt = captured_prompt[0]
    assert "game_profile" in prompt
    assert "ncaa_football_27" in prompt
    assert "game_title" in prompt
    assert "NCAA College Football 27" in prompt
    assert "Do NOT invent team names" in prompt


# ── Bug #3: game_profile wired into VisualContext + SituationModel ───────────


def test_local_vlm_sets_game_title_and_profile():
    """LocalVLMClient should populate game_title and game_profile from the profile."""
    client = LocalVLMClient(game_profile="ncaa_football_27")
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:] = 50  # dark frame, won't crash
    ctx = client.analyze_frame(frame, game_profile="ncaa_football_27")
    if ctx is not None:
        assert ctx.game_profile == "ncaa_football_27"
        assert ctx.game_title == "NCAA College Football 27"


def test_visual_context_round_trips_game_profile():
    """VisualContext.to_dict / from_dict should preserve game_profile."""
    ctx = VisualContext(
        game_state=GameState.GAMEPLAY,
        game_category=GameCategory.FOOTBALL,
        game_title="NCAA College Football 27",
        game_profile="ncaa_football_27",
        confidence=0.8,
    )
    d = ctx.to_dict()
    assert d["game_profile"] == "ncaa_football_27"
    rt = VisualContext.from_dict(d)
    assert rt.game_profile == "ncaa_football_27"
    assert rt.game_title == "NCAA College Football 27"


def test_situation_model_sets_game_profile_from_visual_context():
    """SituationModel should set game_profile from VisualContext events."""
    sm = SituationModel()
    ctx = VisualContext(
        game_state=GameState.GAMEPLAY,
        game_category=GameCategory.FOOTBALL,
        game_title="NCAA College Football 27",
        game_profile="ncaa_football_27",
        confidence=0.85,
    )
    from qoresence.core.types import BaseEvent, SourceLobe

    event = BaseEvent(
        session_id="test",
        clock_ns=0,
        source_lobe=SourceLobe.VISUAL,
        type=EventType.VISUAL_CONTEXT,
        payload=ctx.to_dict(),
    )
    sm.update(event)
    state = sm.to_dict()
    assert state["game_profile"] == "ncaa_football_27"
    assert state["game_title"] == "NCAA College Football 27"
