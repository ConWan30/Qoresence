"""Tests for the VLM-driven Outcome lobe."""

import json
import tempfile
from pathlib import Path

import pytest

from qoresence.core import (
    EventType,
    GameProfileId,
    OutcomeConfig,
    RetinaEventBus,
    SessionAuthority,
    SourceLobe,
)
from qoresence.lobes.outcome import OutcomeRuntime, OutcomeTrigger
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


class TestOutcomeRuntimeVLM:
    """Tests for the VLM-driven OutcomeRuntime."""

    def test_start_subscribes_to_bus(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="vlm_outcome", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="vlm_outcome")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,
            )

            runtime = OutcomeRuntime(config, bus, identity.session_head_ns)
            assert runtime.start() is True
            assert runtime.is_running() is True
            runtime.stop()
            assert runtime.is_running() is False

    def test_game_detected_triggers_session_start(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="detected", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="detected")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,
            )

            runtime = OutcomeRuntime(config, bus, identity.session_head_ns)
            runtime.start()

            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type=EventType.GAME_DETECTED,
                payload={"profile_id": "ncaa_football_27", "confidence": 0.9},
                session_head_ns=identity.session_head_ns,
            )

            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]
            start_events = [e for e in events if e["type"] == "session_start"]
            assert len(start_events) >= 1
            assert start_events[-1]["source_lobe"] == "outcome"

    def test_score_changed_emitted_from_visual_context(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="score", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="score")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,
            )

            runtime = OutcomeRuntime(config, bus, identity.session_head_ns)
            runtime.start()

            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type=EventType.GAME_DETECTED,
                payload={"profile_id": "ncaa_football_27", "confidence": 0.9},
                session_head_ns=identity.session_head_ns,
            )

            ctx1 = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                home_score=0,
                away_score=0,
                quarter=1,
                down=1,
                yards_to_go=10,
                possession="home",
                confidence=0.9,
            )
            ctx2 = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                home_score=7,
                away_score=0,
                quarter=1,
                down=1,
                yards_to_go=10,
                possession="home",
                confidence=0.9,
            )

            bus.emit_raw(
                source_lobe=SourceLobe.VISUAL,
                event_type=EventType.VISUAL_CONTEXT,
                payload=ctx1.to_dict(),
                session_head_ns=identity.session_head_ns,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.VISUAL,
                event_type=EventType.VISUAL_CONTEXT,
                payload=ctx2.to_dict(),
                session_head_ns=identity.session_head_ns,
            )

            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]
            score_events = [
                e
                for e in events
                if e["type"] == "outcome_event"
                and e["payload"].get("event_name") == "score_changed"
            ]
            assert len(score_events) == 1
            assert score_events[0]["payload"]["fields"]["home_score"] == 7

    def test_first_down_emitted_when_down_resets(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="first", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="first")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,
            )

            runtime = OutcomeRuntime(config, bus, identity.session_head_ns)
            runtime.start()

            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type=EventType.GAME_DETECTED,
                payload={"profile_id": "ncaa_football_27", "confidence": 0.9},
                session_head_ns=identity.session_head_ns,
            )

            ctx1 = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                down=3,
                yards_to_go=4,
                confidence=0.9,
            )
            ctx2 = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                down=1,
                yards_to_go=10,
                confidence=0.9,
            )

            bus.emit_raw(
                source_lobe=SourceLobe.VISUAL,
                event_type=EventType.VISUAL_CONTEXT,
                payload=ctx1.to_dict(),
                session_head_ns=identity.session_head_ns,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.VISUAL,
                event_type=EventType.VISUAL_CONTEXT,
                payload=ctx2.to_dict(),
                session_head_ns=identity.session_head_ns,
            )

            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]
            first_downs = [
                e
                for e in events
                if e["type"] == "outcome_event" and e["payload"].get("event_name") == "first_down"
            ]
            assert len(first_downs) == 1

    def test_quarter_changed_emitted(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="quarter", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="quarter")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,
            )

            runtime = OutcomeRuntime(config, bus, identity.session_head_ns)
            runtime.start()

            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type=EventType.GAME_DETECTED,
                payload={"profile_id": "ncaa_football_27", "confidence": 0.9},
                session_head_ns=identity.session_head_ns,
            )

            ctx1 = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                quarter=1,
                confidence=0.9,
            )
            ctx2 = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                quarter=2,
                confidence=0.9,
            )

            bus.emit_raw(
                source_lobe=SourceLobe.VISUAL,
                event_type=EventType.VISUAL_CONTEXT,
                payload=ctx1.to_dict(),
                session_head_ns=identity.session_head_ns,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.VISUAL,
                event_type=EventType.VISUAL_CONTEXT,
                payload=ctx2.to_dict(),
                session_head_ns=identity.session_head_ns,
            )

            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]
            quarters = [
                e
                for e in events
                if e["type"] == "outcome_event"
                and e["payload"].get("event_name") == "quarter_changed"
            ]
            assert len(quarters) == 1

    def test_low_confidence_visual_context_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="lowconf", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="lowconf")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.7,
            )

            runtime = OutcomeRuntime(config, bus, identity.session_head_ns)
            runtime.start()

            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type=EventType.GAME_DETECTED,
                payload={"profile_id": "ncaa_football_27", "confidence": 0.9},
                session_head_ns=identity.session_head_ns,
            )

            ctx = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                home_score=7,
                away_score=0,
                confidence=0.3,
            )

            bus.emit_raw(
                source_lobe=SourceLobe.VISUAL,
                event_type=EventType.VISUAL_CONTEXT,
                payload=ctx.to_dict(),
                session_head_ns=identity.session_head_ns,
            )

            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]
            outcome = [e for e in events if e["type"] == "outcome_event"]
            assert len(outcome) == 0

    def test_menu_visual_context_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="menu", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="menu")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,
            )

            runtime = OutcomeRuntime(config, bus, identity.session_head_ns)
            runtime.start()

            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type=EventType.GAME_DETECTED,
                payload={"profile_id": "ncaa_football_27", "confidence": 0.9},
                session_head_ns=identity.session_head_ns,
            )

            ctx = VisualContext(
                game_state=GameState.MENU,
                game_category=GameCategory.FOOTBALL,
                home_score=7,
                away_score=0,
                confidence=0.9,
            )

            bus.emit_raw(
                source_lobe=SourceLobe.VISUAL,
                event_type=EventType.VISUAL_CONTEXT,
                payload=ctx.to_dict(),
                session_head_ns=identity.session_head_ns,
            )

            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]
            outcome = [e for e in events if e["type"] == "outcome_event"]
            assert len(outcome) == 0

    def test_profile_switches_on_game_detected(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="switch", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="switch")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,
            )

            runtime = OutcomeRuntime(config, bus, identity.session_head_ns)
            runtime.start()

            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type=EventType.GAME_DETECTED,
                payload={"profile_id": "call_of_duty", "confidence": 0.9},
                session_head_ns=identity.session_head_ns,
            )

            assert runtime._profile.profile_id == GameProfileId.CALL_OF_DUTY

            runtime.stop()


class TestOutcomeTrigger:
    """Tests for OutcomeTrigger external interface."""

    def test_trigger_emits_valid_ncaa_events(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="trigger_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="trigger_test")

            trigger = OutcomeTrigger(bus, identity.session_head_ns, GameProfileId.NCAA_FOOTBALL_27)

            # Valid NCAA events
            assert trigger.emit("snap", {"ball_position": "own_35"}) is True
            assert trigger.emit("score_changed", {"home_score": 7, "away_score": 0}) is True
            assert trigger.emit("first_down", {"down": 1, "yards_to_go": 10}) is True
            assert trigger.emit("possession_changed", {"possession": "home"}) is True

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            outcome_events = [e for e in events if e["type"] == "outcome_event"]
            assert len(outcome_events) == 4

            for e in outcome_events:
                assert e["session_id"] == "trigger_test"
                assert e["source_lobe"] == "outcome"
                assert "clock_ns" in e
                assert "session_head_ns" in e
                assert e["payload"]["profile_id"] == "ncaa_football_27"
                assert "event_name" in e["payload"]
                assert "fields" in e["payload"]

    def test_trigger_emits_valid_cod_events(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="cod_trigger", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="cod_trigger")

            trigger = OutcomeTrigger(bus, identity.session_head_ns, GameProfileId.CALL_OF_DUTY)

            # Valid CoD events
            assert trigger.emit("kill", {"victim": "Player1", "weapon": "AK-74u"}) is True
            assert trigger.emit("death", {"killer": "Player2"}) is True
            assert trigger.emit("streak", {"streak_count": 5}) is True

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            outcome_events = [e for e in events if e["type"] == "outcome_event"]
            assert len(outcome_events) == 3

            for e in outcome_events:
                assert e["payload"]["profile_id"] == "call_of_duty"

    def test_trigger_rejects_invalid_event(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="reject_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="reject_test")

            trigger = OutcomeTrigger(bus, identity.session_head_ns, GameProfileId.NCAA_FOOTBALL_27)

            # Invalid event for NCAA
            assert trigger.emit("kill", {}) is False  # CoD event
            assert trigger.emit("spike_plant", {}) is False  # Valorant event

    def test_trigger_confidence_parameter(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="conf_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="conf_test")

            trigger = OutcomeTrigger(bus, identity.session_head_ns, GameProfileId.NCAA_FOOTBALL_27)

            assert trigger.emit("snap", {}, confidence=0.95) is True

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            outcome_events = [e for e in events if e["type"] == "outcome_event"]
            assert outcome_events[0]["payload"]["confidence"] == 0.95


class TestScoreMergeInvariants:
    """VLM lock > OCR; null/partial frames must not wipe cached state."""

    def test_null_score_does_not_wipe_existing_score(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="null_score", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="null_score")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,
            )
            runtime = OutcomeRuntime(config, bus, identity.session_head_ns)
            runtime.start()

            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type=EventType.GAME_DETECTED,
                payload={"profile_id": "ncaa_football_27", "confidence": 0.9},
                session_head_ns=identity.session_head_ns,
            )

            ctx1 = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                home_score=17,
                away_score=0,
                quarter=2,
                down=2,
                yards_to_go=7,
                possession="home",
                field_position="home 35",
                play_clock=25,
                confidence=0.9,
            )
            ctx2 = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                home_score=None,  # partial / dirty frame
                away_score=None,
                quarter=None,
                down=None,
                possession=None,
                field_position=None,
                play_clock=None,
                confidence=0.9,
            )

            bus.emit_raw(
                source_lobe=SourceLobe.VISUAL,
                event_type=EventType.VISUAL_CONTEXT,
                payload=ctx1.to_dict(),
                session_head_ns=identity.session_head_ns,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.VISUAL,
                event_type=EventType.VISUAL_CONTEXT,
                payload=ctx2.to_dict(),
                session_head_ns=identity.session_head_ns,
            )

            runtime.stop()

            assert runtime._home_score == 17
            assert runtime._away_score == 0
            assert runtime._quarter == 2
            assert runtime._down == 2
            assert runtime._possession == "home"
            assert runtime._field_position == "home 35"
            assert runtime._play_clock == 25

    def test_vlm_locked_score_overrides_bad_ocr(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="vlm_lock", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="vlm_lock")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,
            )
            runtime = OutcomeRuntime(config, bus, identity.session_head_ns)
            runtime.start()

            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type=EventType.GAME_DETECTED,
                payload={"profile_id": "ncaa_football_27", "confidence": 0.9},
                session_head_ns=identity.session_head_ns,
            )

            # Initial plausible state
            ctx1 = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                home_score=17,
                away_score=17,
                quarter=2,
                confidence=0.9,
            )
            # A bad OCR-style single-frame drop 17 -> 2 should be rejected.
            ctx_bad = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                home_score=2,
                away_score=17,
                quarter=2,
                confidence=0.9,
            )
            # VLM then corrects cleanly.
            ctx_vlm = VisualContext(
                game_state=GameState.GAMEPLAY,
                game_category=GameCategory.FOOTBALL,
                home_score=17,
                away_score=17,
                quarter=2,
                confidence=0.95,
            )

            for ctx in (ctx1, ctx_bad, ctx_vlm):
                bus.emit_raw(
                    source_lobe=SourceLobe.VISUAL,
                    event_type=EventType.VISUAL_CONTEXT,
                    payload=ctx.to_dict(),
                    session_head_ns=identity.session_head_ns,
                )

            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]
            score_events = [
                e
                for e in events
                if e["type"] == "outcome_event"
                and e["payload"].get("event_name") == "score_changed"
            ]
            assert len(score_events) == 0
            assert runtime._home_score == 17
            assert runtime._away_score == 17


class TestOutcomeConfigDefaults:
    """Tests for OutcomeConfig defaults."""

    def test_defaults(self):
        config = OutcomeConfig()
        assert config.enabled is False
        assert config.game_profile == GameProfileId.NCAA_FOOTBALL_27
        assert config.detection_method == "ocr"
        assert config.confidence_threshold == 0.7
        assert config.poll_interval_s == 2.0


class TestProfileRegistry:
    """Tests for game profile registry."""

    def test_ncaa_profile_registered(self):
        from qoresence.core import GAME_PROFILE_REGISTRY

        assert GameProfileId.NCAA_FOOTBALL_27 in GAME_PROFILE_REGISTRY

    def test_cod_profile_registered(self):
        from qoresence.core import GAME_PROFILE_REGISTRY

        assert GameProfileId.CALL_OF_DUTY in GAME_PROFILE_REGISTRY

    def test_profiles_equal_citizens(self):
        """Both profiles should have equal status in registry."""
        from qoresence.core import GAME_PROFILE_REGISTRY

        ncaa = GAME_PROFILE_REGISTRY[GameProfileId.NCAA_FOOTBALL_27]
        cod = GAME_PROFILE_REGISTRY[GameProfileId.CALL_OF_DUTY]

        # Both should have event_types and outcome_fields
        assert len(ncaa.event_types) > 0
        assert len(cod.event_types) > 0
        assert len(ncaa.outcome_fields) > 0
        assert len(cod.outcome_fields) > 0

        # Categories should differ
        assert ncaa.category == "football"
        assert cod.category == "shooter"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
