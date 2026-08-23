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
    TwitchHelixClient,
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
        moments = scorer.score(state, event_type="outcome_event", event_payload=payload)
        assert any(m.triggered and m.action == "chat" for m in moments)
        chat = next(m for m in moments if m.triggered and m.action == "chat")
        assert "Score update" in chat.message

    def test_menu_state_is_ignored(self):
        scorer = MomentScorer()
        state = SituationState(game_state="menu")
        moments = scorer.score(
            state, event_type="outcome_event", event_payload={"event_name": "score_changed"}
        )
        assert not any(m.triggered for m in moments)

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
        assert any(m.triggered for m in m1)

        m2 = scorer.score(state, event_type="outcome_event", event_payload=payload)
        assert not any(m.triggered for m in m2)

    def test_score_changed_can_trigger_clip(self):
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
        moments = scorer.score(
            state,
            event_type="outcome_event",
            event_payload=payload,
            features={"chat", "clip"},
        )
        assert any(m.action == "clip" for m in moments)


    def test_q2_score_delta_clips_even_when_not_clutch_weight(self):
        scorer = MomentScorer()
        state = SituationState(
            game_state="gameplay",
            game_profile="ncaa_football_27",
            home_score=7,
            away_score=14,
            quarter=2,
        )
        payload = {
            "event_name": "score_changed",
            "fields": {
                "away_score": 13,
                "prev_away_score": 7,
                "home_score": 14,
            },
        }
        moments = scorer.score(
            state,
            event_type="outcome_event",
            event_payload=payload,
            features={"chat", "clip"},
        )
        assert any(m.triggered and m.action == "clip" for m in moments)


    def test_first_lock_0_0_does_not_clip(self):
        scorer = MomentScorer()
        state = SituationState(game_state="gameplay", game_profile="ncaa_football_27", quarter=1)
        payload = {
            "event_name": "score_changed",
            "fields": {"home_score": 0, "away_score": 0},
        }
        moments = scorer.score(
            state,
            event_type="outcome_event",
            event_payload=payload,
            features={"chat", "clip"},
        )
        assert not any(m.action == "clip" and m.triggered for m in moments)

    def test_visual_context_can_start_prediction(self):
        scorer = MomentScorer()
        state = SituationState(
            game_state="gameplay",
            game_profile="ncaa_football_27",
            home_score=14,
            away_score=14,
            quarter=4,
            down=1,
            field_position="opp 10",
            possession="home",
        )
        moments = scorer.score(
            state,
            event_type="visual_context",
            features={"chat", "prediction"},
        )
        assert any(m.action == "start_prediction" for m in moments)


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
            bus.close()

    def test_game_detected_silent_without_ticket(self):
        from qoresence.sync.coupling_ticket import reset_coupling_book

        reset_coupling_book()
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
            assert agent_actions == []
            bus.close()

    def test_outcome_event_triggers_chat_action(self):
        from qoresence.vision.confirm_ticket import get_ticket_book, mint_confirm_ticket

        ticket = mint_confirm_ticket(
            session_id="clutch",
            clock_ns=4,
            home_score=21,
            away_score=14,
        )
        get_ticket_book().put(ticket)
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
            bus.close()


class TestTwitchHelixClient:
    """Tests for the Twitch Helix client with mocked requests."""

    def test_create_clip(self):
        client = TwitchHelixClient(
            client_id="test_client",
            access_token="test_token",
            broadcaster_id="12345",
        )
        with patch.object(client._session, "post") as mock_post:
            resp = MagicMock()
            resp.status_code = 202
            resp.ok = True
            resp.json.return_value = {
                "data": [
                    {
                        "id": "CuriousDeliciousApple123",
                        "edit_url": "https://clips.twitch.tv/edit/CuriousDeliciousApple123",
                        "created_at": "2026-08-06T00:00:00Z",
                    }
                ]
            }
            mock_post.return_value = resp

            clip = client.create_clip()
            assert clip is not None
            assert clip.id == "CuriousDeliciousApple123"
            assert "clips.twitch.tv" in clip.edit_url

    def test_create_and_resolve_prediction(self):
        client = TwitchHelixClient(
            client_id="test_client",
            access_token="test_token",
            broadcaster_id="12345",
        )
        with (
            patch.object(client._session, "post") as mock_post,
            patch.object(client._session, "patch") as mock_patch,
        ):
            post_resp = MagicMock()
            post_resp.status_code = 201
            post_resp.ok = True
            post_resp.json.return_value = {
                "data": [
                    {
                        "id": "pred-1",
                        "title": "Score on this drive?",
                        "outcomes": [
                            {"id": "out-yes", "title": "Yes"},
                            {"id": "out-no", "title": "No"},
                        ],
                        "status": "ACTIVE",
                    }
                ]
            }
            mock_post.return_value = post_resp

            pred = client.create_prediction("Score on this drive?", ["Yes", "No"], 120)
            assert pred is not None
            assert pred.id == "pred-1"
            assert client.active_prediction is not None

            patch_resp = MagicMock()
            patch_resp.status_code = 200
            patch_resp.ok = True
            patch_resp.json.return_value = {"data": [{"id": "pred-1", "status": "RESOLVED"}]}
            mock_patch.return_value = patch_resp

            assert client.resolve_prediction(0) is True
            assert client.active_prediction is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
