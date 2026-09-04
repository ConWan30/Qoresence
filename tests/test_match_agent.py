"""Match-observer agent — Quicksilver glm-5.3-flash wiring. Observation only."""

from __future__ import annotations

from qoresence.agents.llm_client import DEFAULT_BASE_URL, DEFAULT_MODEL, LLMConfig
from qoresence.agents.match_agent import (
    MatchAgent,
    build_match_evidence,
    evidence_ticket_id,
)
from qoresence.sync.hid_domain import HidDomain
from qoresence.vision.confirm_ticket import mint_confirm_ticket
from qoresence.vision.picture_hid_ticket import mint_picture_hid_ticket


def test_llm_config_from_quicksilver_env_matches_clutchbot_path():
    cfg = LLMConfig.from_quicksilver_env(enabled=False)
    assert cfg.provider == "quicksilver"
    assert cfg.model == DEFAULT_MODEL
    assert cfg.model == "glm-5.3-flash"
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.enabled is False


def test_clutchbot_chat_and_confirm_vision_use_separate_config_paths():
    """Chat stays glm-5.3-flash; confirm VLM is gemini-3.8-flash; distinct factories."""
    from qoresence.agents.llm_client import DEFAULT_VISION_MODEL

    chat_cfg = LLMConfig.from_quicksilver_env(enabled=False)
    vision_cfg = LLMConfig.from_scoreboard_vlm()
    assert chat_cfg.model == DEFAULT_MODEL == "glm-5.3-flash"
    assert vision_cfg.model == DEFAULT_VISION_MODEL == "gemini-3.8-flash"
    assert chat_cfg.model != vision_cfg.model
    assert chat_cfg is not vision_cfg
    assert vision_cfg.max_tokens == 400
    assert chat_cfg.max_tokens == 180
    assert vision_cfg.timeout_s == 14.0
    assert chat_cfg.timeout_s == 8.0


def test_evidence_no_scores_without_confirm():
    bag = build_match_evidence(
        civif={
            "board_locked": True,
            "controller_bodied": False,
            "situation": {"home_score": 21, "away_score": 13},
            "input_ticks": [{"button": "R2"}],
        }
    )
    assert bag["home_score"] is None
    assert bag["away_score"] is None
    assert bag["board_locked"] is False
    assert bag["input_ticks"] == []
    assert bag["controller_bodied"] is False


def test_evidence_scores_only_with_confirm_ticket():
    t = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=21,
        away_score=13,
        home_team="DAL",
        away_team="NO",
    )
    bag = build_match_evidence(confirm=t, civif={"controller_bodied": False})
    assert bag["home_score"] == 21
    assert bag["away_score"] == 13
    assert bag["confirm_ticket_id"] == t.ticket_id
    assert bag["board_locked"] is True


def test_evidence_picture_label_is_not_a_pad_press():
    pic = mint_picture_hid_ticket(
        clock_ns=2,
        frame_seq=9,
        hid_button="R2",
        prompt_text="Sprint",
        game_state="gameplay",
    )
    bag = build_match_evidence(
        picture=pic,
        civif={"controller_bodied": False, "frame_seq": 9, "input_ticks": [{"button": "R2"}]},
    )
    assert bag["picture_hid"]["hid_button"] == "R2"
    assert bag["picture_hid"]["hid_domain"] == HidDomain.PICTURE.value
    assert bag["input_ticks"] == []
    assert evidence_ticket_id(bag) == pic.ticket_id


def test_evidence_bodied_keeps_input_ticks():
    bag = build_match_evidence(
        civif={
            "controller_bodied": True,
            "input_ticks": [{"button": "Cross", "edge_type": "press", "clock_ns": 3}],
        }
    )
    assert bag["controller_bodied"] is True
    assert bag["input_ticks"][0]["button"] == "Cross"


def test_propose_stub_without_live_llm():
    agent = MatchAgent(enabled=False)
    assert agent.live is False
    pic = mint_picture_hid_ticket(
        clock_ns=2, frame_seq=4, hid_button="Cross", game_state="gameplay"
    )
    bag = build_match_evidence(picture=pic)
    out = agent.propose(bag)
    assert out["ok"] is True
    assert out["live"] is False
    assert "pad press" in out["text"].lower() or "Cross" in out["text"]
    assert out["model"] == "stub-match-agent"


def test_propose_hold_without_tickets():
    agent = MatchAgent(enabled=False)
    out = agent.propose(build_match_evidence(civif={"controller_bodied": False}))
    assert out["path"] == "hold"
    assert out["ticket_id"] == ""


def test_match_agent_default_off():
    agent = MatchAgent(enabled=False)
    assert agent.enabled is False
    assert agent.start() is False


def test_surface_last_note_off():
    """Empty when agent is None or enabled=False."""
    from qoresence.agents.match_agent import surface_last_note, start_match_agent

    start_match_agent(enabled=False)
    result = surface_last_note()
    assert result == {}


def test_surface_last_note_quiet():
    """Empty when last_note is None."""
    from qoresence.agents.match_agent import MatchAgent, surface_last_note

    agent = MatchAgent(enabled=True)
    agent.live = True
    agent._last = None
    from qoresence.agents import match_agent

    match_agent._agent = agent
    result = surface_last_note()
    assert result == {}
    match_agent._agent = None


def test_surface_last_note_unlicensed():
    """Empty when live=False (stub) even if ticket_id present."""
    from qoresence.agents.match_agent import MatchAgent, surface_last_note

    agent = MatchAgent(enabled=True)
    agent.live = False
    note = {
        "ok": True,
        "live": False,
        "text": "Stub text should not appear",
        "ticket_id": "stub-ticket",
        "path": "fast",
        "model": "stub",
        "evidence": {},
    }
    agent._last = note
    from qoresence.agents import match_agent

    match_agent._agent = agent
    result = surface_last_note()
    assert result == {}
    match_agent._agent = None


def test_surface_last_note_licensed():
    """Returns ok=True with text when live=True + ticket_id + path=confirm/fast + text."""
    from qoresence.agents.match_agent import MatchAgent, surface_last_note

    agent = MatchAgent(enabled=True)
    agent.live = True
    note = {
        "ok": True,
        "live": True,
        "text": "DAL 21 NO 13 on this frame",
        "ticket_id": "test-ticket-123",
        "path": "confirm",
        "model": "test-model",
        "evidence": {},
    }
    agent._last = note
    from qoresence.agents import match_agent

    match_agent._agent = agent
    result = surface_last_note()
    assert result["ok"] is True
    assert result["text"] == "DAL 21 NO 13 on this frame"
    assert result["live"] is True
    assert result["ticket_id"] == "test-ticket-123"
    assert result["path"] == "confirm"
    assert result["model"] == "test-model"
    match_agent._agent = None


def test_situation_payload_carries_match_agent():
    """_situation_payload()["match_agent"] is empty when agent is off."""
    from unittest.mock import patch

    from qoresence.deck.server import _situation_payload

    with patch("qoresence.agents.match_agent.get_match_agent", return_value=None):
        out = _situation_payload()
        assert "match_agent" in out
        assert out["match_agent"] == {}
