"""Tests for ClutchBot agent."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from qoresence.agents import (
    ActionExecutor,
    ClutchBotAgent,
    MomentScorer,
    SessionMemory,
    SituationModel,
    TwitchIRCClient,
)
from qoresence.agents.moment_scorer import ScoredMoment
from qoresence.agents.situation_model import SituationState
from qoresence.core import (
    BaseEvent,
    ClutchBotConfig,
    EventType,
    GameProfileId,
    RetinaEventBus,
    SessionAuthority,
    SourceLobe,
    TwitchConfig,
    clock_ns,
)
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


class TestTwitchIRCClient:
    """Tests for the minimal Twitch IRC client."""

    def test_send_message_trims_to_500_chars(self):
        client = TwitchIRCClient(
            username="testbot",
            oauth_token="testtoken",
            channel="testchannel",
        )
        with patch.object(client, "_sock", new=MagicMock()):
            client._ready_event.set()
            client._running = True
            long_msg = "x" * 600
            assert client.send_message(long_msg) is True
            queued = client._outbound.get(timeout=1.0)
            assert len(queued) == 500

    def test_drop_message_when_not_ready(self):
        client = TwitchIRCClient(
            username="testbot",
            oauth_token="testtoken",
            channel="testchannel",
        )
        assert client.send_message("hello") is False


class TestSituationModel:
    """Tests for the rolling situation model."""

    def test_visual_context_updates_football_state(self):
        model = SituationModel()
        ctx = VisualContext(
            game_state=GameState.GAMEPLAY,
            game_category=GameCategory.FOOTBALL,
            game_title="NCAA Football 27",
            home_score=14,
            away_score=7,
            quarter=2,
            down=1,
            yards_to_go=10,
            possession="home",
            confidence=0.9,
        )
        event = BaseEvent(
            session_id="test",
            clock_ns=clock_ns(),
            source_lobe=SourceLobe.VISUAL,
            type=EventType.VISUAL_CONTEXT,
            payload=ctx.to_dict(),
        )
        model.update(event)

        assert model.state.game_state == "gameplay"
        assert model.state.home_score == 14
        assert model.state.away_score == 7
        assert model.state.quarter == 2
        assert model.state.down == 1

    def test_controller_events_compute_apm(self):
        model = SituationModel(window_s=5.0)
        now = clock_ns()
        for i in range(10):
            event = BaseEvent(
                session_id="test",
                clock_ns=now + i * 100_000_000,
                source_lobe=SourceLobe.CONTROLLER,
                type=EventType.CONTROLLER_EVENT,
                payload={"button": "x", "value": 1.0},
            )
            model.update(event)

        assert model.state.controller.apm_5s > 0

    def test_to_dict_serializes(self):
        model = SituationModel()
        d = model.to_dict()
        assert "game_state" in d
        assert "controller_apm" in d


class TestMomentScorer:
    """Tests for moment scoring."""

    def test_score_changed_in_gameplay_triggers(self):
        scorer = MomentScorer()
        state = SituationState(
            game_state="gameplay",
            game_profile="ncaa_football_27",
            home_score=14,
            away_score=14,
            quarter=4,
            down=1,
            yards_to_go=10,
            possession="home",
        )
        payload = {
            "event_name": "score_changed",
            "profile_id": "ncaa_football_27",
            "confidence": 0.9,
            "fields": {"home_score": 21, "away_score": 14, "prev_home_score": 14},
        }
        moment = scorer.score(state, event_type="outcome_event", event_payload=payload)
        assert moment.triggered is True
        assert moment.action == "chat"
        assert "Score update" in moment.message

    def test_menu_state_is_ignored(self):
        scorer = MomentScorer()
        state = SituationState(game_state="menu")
        moment = scorer.score(state, event_type="outcome_event", event_payload={"event_name": "score_changed"})
        assert moment.triggered is False

    def test_cooldown_prevents_spam(self):
        scorer = MomentScorer()
        state = SituationState(
            game_state="gameplay",
            game_profile="ncaa_football_27",
            home_score=14,
            away_score=14,
            quarter=4,
            down=1,
            yards_to_go=10,
            possession="home",
        )
        payload = {
            "event_name": "score_changed",
            "profile_id": "ncaa_football_27",
            "confidence": 0.9,
            "fields": {"home_score": 21, "away_score": 14},
        }

        m1 = scorer.score(state, event_type="outcome_event", event_payload=payload)
        assert m1.triggered is True

        m2 = scorer.score(state, event_type="outcome_event", event_payload=payload)
        assert m2.triggered is False  # cooldown


class TestActionExecutor:
    """Tests for the action executor."""

    def test_execute_dispatches_to_backends(self):
        backend = MagicMock(spec=["name", "start", "stop", "execute"])
        backend.name.return_value = "mock"
        backend.start.return_value = True
        backend.execute.return_value = True

        executor = ActionExecutor([backend])
        assert executor.start() is True

        moment = ScoredMoment(
            triggered=True,
            weight=0.9,
            action="chat",
            message="hello chat",
            reason="test",
            cooldown_key="test",
        )
        results = executor.execute(moment, context={"session_id": "x"})
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].backend == "mock"

        executor.stop()

    def test_untriggered_moment_is_ignored(self):
        executor = ActionExecutor([])
        moment = ScoredMoment(
            triggered=False,
            weight=0.0,
            action="none",
            message="",
            reason="",
            cooldown_key="",
        )
        assert executor.execute(moment) == []


class TestSessionMemory:
    """Tests for session memory writer."""

    def test_record_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.jsonl"
            memory = SessionMemory(output_path=path)
            model = SituationModel()
            moment = ScoredMoment(
                triggered=True,
                weight=0.9,
                action="chat",
                message="hello",
                reason="test",
                cooldown_key="test",
            )
            memory.record(moment, model, [{"backend": "mock", "success": True}])

            lines = path.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["moment"]["message"] == "hello"


class TestClutchBotAgent:
    """Tests for the full ClutchBot agent."""

    def test_start_subscribes_to_bus(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="clutch", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="clutch")
            config = ClutchBotConfig(enabled=True, twitch=TwitchConfig(enabled=False))
            agent = ClutchBotAgent(config, bus, identity.session_head_ns)

            assert agent.start() is True
            assert agent.is_running() is True
            agent.stop()
            assert agent.is_running() is False

    def test_game_detected_emits_agent_action(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="clutch", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="clutch")
            config = ClutchBotConfig(enabled=True, twitch=TwitchConfig(enabled=False))
            agent = ClutchBotAgent(config, bus, identity.session_head_ns)
            agent.start()

            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type=EventType.GAME_DETECTED,
                payload={"profile_id": GameProfileId.NCAA_FOOTBALL_27.value, "confidence": 0.9},
                session_head_ns=identity.session_head_ns,
            )

            agent.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]
            agent_actions = [e for e in events if e["type"] == "agent_action"]
            assert len(agent_actions) >= 1
            assert agent_actions[0]["source_lobe"] == "agent"

    def test_outcome_event_triggers_chat_action(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="clutch", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="clutch")

            config = ClutchBotConfig(
                enabled=True,
                message_cooldown_s=0.0,
                twitch=TwitchConfig(enabled=False),
            )
            agent = ClutchBotAgent(config, bus, identity.session_head_ns)
            agent.start()

            # Seed visual context
            ctx = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                home_score=14,
                away_score=14,
                quarter=4,
                down=1,
                yards_to_go=10,
                possession="home",
                confidence=0.9,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.VISUAL,
                event_type=EventType.VISUAL_CONTEXT,
                payload=ctx.to_dict(),
                session_head_ns=identity.session_head_ns,
            )

            bus.emit_raw(
                source_lobe=SourceLobe.OUTCOME,
                event_type=EventType.OUTCOME_EVENT,
                payload={
                    "event_name": "score_changed",
                    "profile_id": GameProfileId.NCAA_FOOTBALL_27.value,
                    "confidence": 0.9,
                    "fields": {"home_score": 21, "away_score": 14},
                },
                session_head_ns=identity.session_head_ns,
            )

            agent.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]
            agent_actions = [e for e in events if e["type"] == "agent_action"]
            assert len(agent_actions) >= 1
            assert agent_actions[0]["payload"]["action"] == "chat"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
