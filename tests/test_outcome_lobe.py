"""
Phase 5 Tests — Outcome Lobe

Tests for NCAA Football 27 and Call of Duty profile loading,
event emission, OutcomeTrigger, and detector framework.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest

from qoresence.core import (
    RetinaEventBus,
    SourceLobe,
    EventType,
    OutcomeConfig,
    GameProfileId,
    GameProfile,
    NCAA_FOOTBALL_27_PROFILE,
    CALL_OF_DUTY_PROFILE,
    clock_ns,
    SessionAuthority,
)
from qoresence.lobes.outcome import OutcomeRuntime, OutcomeTrigger


class TestOutcomeRuntime:
    """Tests for OutcomeRuntime core functionality."""

    def test_runtime_creation_ncaa(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="test_session", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="test_session")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                detection_method="ocr",
                confidence_threshold=0.7,
                poll_interval_s=0.5,
            )

            runtime = OutcomeRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            assert runtime._profile.profile_id == GameProfileId.NCAA_FOOTBALL_27
            assert runtime._profile.display_name == "NCAA College Football 27"
            assert "snap" in runtime._detectors
            assert "score_changed" in runtime._detectors

    def test_runtime_creation_cod(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="test_session", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="test_session")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.CALL_OF_DUTY,
                detection_method="ocr",
                confidence_threshold=0.7,
                poll_interval_s=0.5,
            )

            runtime = OutcomeRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            assert runtime._profile.profile_id == GameProfileId.CALL_OF_DUTY
            assert runtime._profile.display_name == "Call of Duty (Warzone / Multiplayer)"
            assert "kill" in runtime._detectors
            assert "death" in runtime._detectors
            assert "streak" in runtime._detectors

    def test_ncaa_event_types_complete(self):
        """Verify all NCAA Football 27 event types have detectors."""
        expected = {
            "snap", "down_advanced", "first_down", "score_changed",
            "playclock_reset", "quarter_changed", "possession_changed",
            "timeout_called", "penalty", "turnover"
        }
        assert set(NCAA_FOOTBALL_27_PROFILE.event_types) == expected

    def test_ncaa_outcome_fields_complete(self):
        """Verify all NCAA Football 27 outcome fields defined."""
        expected = {
            "home_score", "away_score", "quarter", "down",
            "yards_to_go", "possession", "play_clock", "game_clock", "field_position"
        }
        assert set(NCAA_FOOTBALL_27_PROFILE.outcome_fields) == expected

    def test_cod_event_types_complete(self):
        """Verify all Call of Duty event types have detectors."""
        expected = {
            "kill", "death", "assist", "streak",
            "objective_capture", "objective_defend",
            "round_start", "round_end", "match_start", "match_end"
        }
        assert set(CALL_OF_DUTY_PROFILE.event_types) == expected

    def test_cod_outcome_fields_complete(self):
        """Verify all Call of Duty outcome fields defined."""
        expected = {"kills", "deaths", "assists", "score", "streak_count", "team", "mode", "map"}
        assert set(CALL_OF_DUTY_PROFILE.outcome_fields) == expected

    def test_score_changed_detection(self):
        """Test score_changed detector with mocked OCR."""
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="score_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="score_test")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,  # Low for test
            )

            runtime = OutcomeRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            # Mock the _ocr_region method directly
            original_ocr = runtime._ocr_region
            call_count = [0]

            def mock_ocr(frame, region_name):
                call_count[0] += 1
                if region_name == "scoreboard":
                    if call_count[0] == 1:
                        return "21 - 14"
                    return "21 - 14"
                return original_ocr(frame, region_name)

            runtime._ocr_region = mock_ocr

            # Create dummy frame
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)

            # Run detector directly
            result = runtime._detect_score_changed(frame)

            # Should detect change from initial (0,0) to (21,14)
            assert result.detected is True
            assert result.confidence >= 0.5
            assert result.fields.get("home_score") == 21
            assert result.fields.get("away_score") == 14

    def test_quarter_changed_detection(self):
        """Test quarter_changed detector."""
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="quarter_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="quarter_test")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,
            )

            runtime = OutcomeRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            # Mock the _ocr_region method
            original_ocr = runtime._ocr_region
            call_count = [0]

            def mock_ocr(frame, region_name):
                call_count[0] += 1
                if region_name == "quarter":
                    if call_count[0] == 1:
                        return "1"
                    elif call_count[0] == 2:
                        return "2"
                    return "2"  # Third call still returns 2
                return original_ocr(frame, region_name)

            runtime._ocr_region = mock_ocr

            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            result1 = runtime._detect_quarter_changed(frame)
            assert result1.detected is True
            assert result1.fields.get("quarter") == 1

            # Update prev_fields manually (normally done by _emit_outcome_event)
            runtime._prev_fields["quarter"] = 1

            # Second call: Q2 (change detected)
            result2 = runtime._detect_quarter_changed(frame)
            assert result2.detected is True
            assert result2.fields.get("quarter") == 2

            # Update prev_fields
            runtime._prev_fields["quarter"] = 2

            # Third call: still Q2 (no change)
            result3 = runtime._detect_quarter_changed(frame)
            assert result3.detected is False

    def test_ocr_regions_defined(self):
        """Verify OCR regions defined for both profiles."""
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="region_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="region_test")

            # NCAA
            ncaa_config = OutcomeConfig(game_profile=GameProfileId.NCAA_FOOTBALL_27)
            ncaa_runtime = OutcomeRuntime(ncaa_config, bus, identity.session_head_ns)
            assert "scoreboard" in ncaa_runtime._ocr_regions
            assert "down_distance" in ncaa_runtime._ocr_regions
            assert "play_clock" in ncaa_runtime._ocr_regions

            # CoD
            cod_config = OutcomeConfig(game_profile=GameProfileId.CALL_OF_DUTY)
            cod_runtime = OutcomeRuntime(cod_config, bus, identity.session_head_ns)
            assert "kill_feed" in cod_runtime._ocr_regions
            assert "health" in cod_runtime._ocr_regions
            assert "streak" in cod_runtime._ocr_regions


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

            outcome_events = [e for e in events if e['type'] == 'outcome_event']
            assert len(outcome_events) == 4

            for e in outcome_events:
                assert e['session_id'] == 'trigger_test'
                assert e['source_lobe'] == 'outcome'
                assert 'clock_ns' in e
                assert 'session_head_ns' in e
                assert e['payload']['profile_id'] == 'ncaa_football_27'
                assert 'event_name' in e['payload']
                assert 'fields' in e['payload']

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

            outcome_events = [e for e in events if e['type'] == 'outcome_event']
            assert len(outcome_events) == 3

            for e in outcome_events:
                assert e['payload']['profile_id'] == 'call_of_duty'

    def test_trigger_rejects_invalid_event(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="reject_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="reject_test")

            trigger = OutcomeTrigger(bus, identity.session_head_ns, GameProfileId.NCAA_FOOTBALL_27)

            # Invalid event for NCAA
            assert trigger.emit("kill", {}) is False  # CoD event
            assert trigger.emit("touchdown", {}) is False  # Not in NCAA event_types

    def test_trigger_confidence_parameter(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="conf_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="conf_test")

            trigger = OutcomeTrigger(bus, identity.session_head_ns, GameProfileId.NCAA_FOOTBALL_27)

            assert trigger.emit("snap", {}, confidence=0.95) is True

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            outcome_events = [e for e in events if e['type'] == 'outcome_event']
            assert outcome_events[0]['payload']['confidence'] == 0.95


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


class TestOutcomeRuntimeIntegration:
    """Integration tests for OutcomeRuntime with frame provider."""

    def test_frame_provider_integration(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="frame_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="frame_test")

            config = OutcomeConfig(
                enabled=True,
                game_profile=GameProfileId.NCAA_FOOTBALL_27,
                confidence_threshold=0.5,
                poll_interval_s=0.01,  # Fast for test
            )

            runtime = OutcomeRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            # Set frame provider
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            provider_called = []

            def provider():
                provider_called.append(1)
                return frame if len(provider_called) <= 2 else None

            runtime.set_frame_provider(provider)

            runtime.start()
            time.sleep(0.1)  # Let it run a couple iterations
            runtime.stop()

            assert len(provider_called) >= 2

            # Should have session_start and session_end
            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            event_types = [e['type'] for e in events]
            assert 'session_start' in event_types
            assert 'session_end' in event_types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])