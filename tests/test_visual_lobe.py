"""
Phase 8 Tests — Visual Lobe

Tests for VisualRuntime, MockVLMClient, game-state classification,
and cross-modal verification.
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
    SessionAuthority,
    VisualConfig,
)
from qoresence.lobes.visual import CrossModalVerdict, MockVLMClient, VisualContext, VisualRuntime


class TestVisualRuntime:
    """Tests for VisualRuntime core functionality."""

    def test_runtime_creation(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="test_session", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="test_session")

            config = VisualConfig(
                enabled=True,
                model_endpoint="https://test.endpoint",
                model_name="test-model",
                frame_sample_rate=30,
                max_frame_dim=640,
                min_confidence=0.6,
                game_category="football",
            )

            runtime = VisualRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            assert runtime.config == config
            assert runtime.session_head_ns == identity.session_head_ns
            assert not runtime.is_running()

    def test_mock_vlm_football_classification(self):
        """Test MockVLMClient classifies green field as football."""
        config = VisualConfig(game_category="football")
        client = MockVLMClient(config)

        # Create green-field-like frame
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:, :, 1] = 200  # Green channel high

        context = client.analyze_frame(frame, "test prompt")

        assert context is not None
        assert context.game_state.value == "gameplay"
        assert context.game_category.value == "football"
        assert context.confidence > 0.8
        assert context.model == "mock"

    def test_mock_vlm_shooter_classification(self):
        """Test MockVLMClient classifies dark frame as shooter."""
        config = VisualConfig(game_category="shooter")
        client = MockVLMClient(config)

        # Create dark frame
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:, :] = 30  # Dark

        context = client.analyze_frame(frame, "test prompt")

        assert context is not None
        assert context.game_state.value == "gameplay"
        assert context.game_category.value == "shooter"
        assert context.confidence > 0.7

    def test_mock_vlm_cross_modal_confirmed(self):
        """Test MockVLMClient cross-modal with outcome+controller."""
        config = VisualConfig()
        client = MockVLMClient(config)

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        other_modalities = {
            "outcome": {"event": "score_changed"},
            "controller": {"trigger": "R2"},
        }

        verdict = client.cross_modal_check(frame, other_modalities)

        assert verdict is not None
        assert verdict.verdict == "confirmed"
        assert verdict.confidence > 0.8

    def test_mock_vlm_cross_modal_inconclusive(self):
        """Test MockVLMClient cross-modal with insufficient data."""
        config = VisualConfig()
        client = MockVLMClient(config)

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        other_modalities = {"screen": {"motion": 0.1}}

        verdict = client.cross_modal_check(frame, other_modalities)

        assert verdict is not None
        assert verdict.verdict == "inconclusive"
        assert verdict.confidence == 0.5

    @patch("qoresence.lobes.visual.VLMClient")
    def test_visual_context_emission(self, mock_client_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="visual_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="visual_test")

            config = VisualConfig(
                enabled=True,
                frame_sample_rate=1,  # Analyze every frame for test
                min_confidence=0.5,
            )

            # Setup mock client
            mock_client = Mock()
            mock_client.analyze_frame.return_value = VisualContext(
                game_state="football",
                confidence=0.9,
                details={"mock": True},
                model="mock-model",
                latency_ms=50.0,
            )
            mock_client_class.return_value = mock_client

            runtime = VisualRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            # Provide test frame
            test_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            test_frame[:, :, 1] = 200  # Green

            frame_count = [0]

            def frame_provider():
                frame_count[0] += 1
                return test_frame if frame_count[0] <= 2 else None

            runtime.set_frame_provider(frame_provider)

            runtime.start()
            time.sleep(0.2)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            visual_events = [e for e in events if e["source_lobe"] == "visual"]
            context_events = [e for e in visual_events if e["type"] == "visual_context"]

            assert len(context_events) >= 1

            for e in context_events:
                assert e["session_id"] == "visual_test"
                assert e["source_lobe"] == "visual"
                assert "clock_ns" in e
                assert e["payload"]["game_state"] == "gameplay"
                assert e["payload"]["game_category"] == "football"
                assert e["payload"]["confidence"] == 0.9

            bus.close()

    @patch("qoresence.lobes.visual.VLMClient")
    def test_cross_modal_verdict_emission(self, mock_client_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="cross_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="cross_test")

            config = VisualConfig(
                enabled=True,
                frame_sample_rate=1,
                min_confidence=0.5,
            )

            # Setup mock client
            mock_client = Mock()
            mock_client.analyze_frame.return_value = VisualContext(
                game_state="football",
                confidence=0.9,
                details={},
                model="mock",
                latency_ms=10.0,
            )
            mock_client.cross_modal_check.return_value = CrossModalVerdict(
                verdict="confirmed",
                confidence=0.95,
                reasoning="All modalities align",
                modalities_checked=["outcome", "controller"],
            )
            mock_client_class.return_value = mock_client

            runtime = VisualRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            # Frame provider
            test_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

            def frame_provider():
                return test_frame

            runtime.set_frame_provider(frame_provider)

            # Modality provider
            def modality_provider():
                return {
                    "outcome": {"event": "score_changed"},
                    "controller": {"causal_density": 5},
                }

            runtime.set_modality_provider(modality_provider)

            runtime.start()
            time.sleep(0.2)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            visual_events = [e for e in events if e["source_lobe"] == "visual"]
            verdict_events = [e for e in visual_events if e["type"] == "cross_modal_verdict"]

            assert len(verdict_events) >= 1

            for e in verdict_events:
                assert e["payload"]["verdict"] == "confirmed"
                assert e["payload"]["confidence"] == 0.95
                assert "modalities_checked" in e["payload"]

            bus.close()

    def test_session_start_and_end_events(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="session_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="session_test")

            config = VisualConfig(enabled=True)

            runtime = VisualRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.1)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            event_types = [e["type"] for e in events]
            assert "session_start" in event_types
            assert "session_end" in event_types

            start_event = next(e for e in events if e["type"] == "session_start")
            assert start_event["payload"]["model_name"] == config.model_name

            end_event = next(e for e in events if e["type"] == "session_end")
            assert "frames_analyzed" in end_event["payload"]

            bus.close()


class TestVisualConfigDefaults:
    """Tests for VisualConfig defaults."""

    def test_defaults(self):
        config = VisualConfig()
        assert config.enabled is False
        assert config.model_endpoint == "https://api.quicksilverpro.io/v1"
        assert config.model_name == "qwen3.7-flash"
        assert config.api_key is None
        assert config.frame_sample_rate == 30
        assert config.max_frame_dim == 640
        assert config.min_confidence == 0.6
        assert config.game_category == "football"


class TestVisualContext:
    """Tests for VisualContext dataclass."""

    def test_creation(self):
        context = VisualContext(
            game_state="football",
            confidence=0.9,
            details={"test": True},
            model="test-model",
            latency_ms=100.0,
        )
        assert context.game_state.value == "gameplay"
        assert context.game_category.value == "football"
        assert context.confidence == 0.9


class TestCrossModalVerdict:
    """Tests for CrossModalVerdict dataclass."""

    def test_creation(self):
        verdict = CrossModalVerdict(
            verdict="confirmed",
            confidence=0.95,
            reasoning="Test reasoning",
            modalities_checked=["outcome", "controller"],
        )
        assert verdict.verdict == "confirmed"
        assert verdict.confidence == 0.95


class TestVisualRuntimeIntegration:
    """Integration tests with other lobes."""

    @patch("qoresence.lobes.visual.VLMClient")
    def test_integration_with_outcome_and_controller(self, mock_client_class):
        """Test visual lobe receives modality data from outcome and controller."""
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="integ_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="integ_test")

            config = VisualConfig(enabled=True, frame_sample_rate=1, min_confidence=0.5)

            mock_client = Mock()
            mock_client.analyze_frame.return_value = VisualContext(
                game_state="football", confidence=0.9, details={}, model="mock", latency_ms=10.0
            )
            mock_client.cross_modal_check.return_value = CrossModalVerdict(
                verdict="confirmed",
                confidence=0.9,
                reasoning="Match",
                modalities_checked=["outcome", "controller"],
            )
            mock_client_class.return_value = mock_client

            runtime = VisualRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            # Frame with football-like content
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            frame[:, :, 1] = 180  # Green field

            def frame_provider():
                return frame

            runtime.set_frame_provider(frame_provider)

            # Modality provider simulates outcome + controller data
            def modality_provider():
                return {
                    "outcome": {"last_event": "score_changed", "home_score": 21},
                    "controller": {"causal_density": 10, "last_trigger": "R2"},
                    "screen": {"coupling_score": 0.7},
                }

            runtime.set_modality_provider(modality_provider)

            runtime.start()
            time.sleep(0.2)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            visual_events = [e for e in events if e["source_lobe"] == "visual"]
            verdict_events = [e for e in visual_events if e["type"] == "cross_modal_verdict"]

            assert len(verdict_events) >= 1
            verdict = verdict_events[0]["payload"]
            assert verdict["verdict"] == "confirmed"
            assert "outcome" in verdict["modalities_checked"]
            assert "controller" in verdict["modalities_checked"]

            bus.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
