"""
Phase 7 Tests — Screen Lobe

Tests for ScreenRuntime, screen capture, CV coupling score, HUD OCR.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import numpy as np
import pytest

from qoresence.core import (
    RetinaEventBus,
    SourceLobe,
    EventType,
    clock_ns,
    ScreenConfig,
    SessionAuthority,
)
from qoresence.lobes.screen import ScreenRuntime, list_monitors


class MockMSS:
    """Mock mss.mss for testing."""

    def __init__(self):
        self.monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},  # All monitors
            {"left": 0, "top": 0, "width": 1920, "height": 1080},  # Monitor 1
            {"left": 1920, "top": 0, "width": 1920, "height": 1080},  # Monitor 2
        ]
        self._closed = False
        self._frame_counter = 0

    def grab(self, monitor):
        # Return a fake BGRA frame with changing content for motion detection
        h, w = monitor["height"], monitor["width"]
        frame = np.zeros((h, w, 4), dtype=np.uint8)
        # Create a moving pattern - shift a bright region each frame
        x_offset = (self._frame_counter * 10) % w
        y_offset = (self._frame_counter * 5) % h
        frame[y_offset:y_offset+100, x_offset:x_offset+100, 0] = 255  # Blue
        frame[y_offset:y_offset+100, x_offset:x_offset+100, 1] = 255  # Green
        frame[y_offset:y_offset+100, x_offset:x_offset+100, 2] = 255  # Red
        frame[:, :, 3] = 255  # Alpha
        self._frame_counter += 1
        return MockScreenshot(frame)

    def close(self):
        self._closed = True


class MockScreenshot:
    """Mock mss screenshot."""

    def __init__(self, frame):
        self._frame = frame

    def __array__(self):
        return self._frame


class TestScreenRuntime:
    """Tests for ScreenRuntime core functionality."""

    def test_runtime_creation(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="test_session", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="test_session")

            config = ScreenConfig(enabled=True, fps_target=30.0, monitor_index=0)

            runtime = ScreenRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            assert runtime.config == config
            assert runtime.session_head_ns == identity.session_head_ns
            assert not runtime.is_running()

    @patch('qoresence.lobes.screen.mss.mss', return_value=MockMSS())
    def test_start_opens_capture(self, mock_mss_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="capture_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="capture_test")

            config = ScreenConfig(enabled=True, fps_target=30.0, monitor_index=0)

            runtime = ScreenRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            assert runtime.start() is True
            assert runtime.is_running()

            runtime.stop()

    @patch('qoresence.lobes.screen.mss.mss', return_value=MockMSS())
    def test_motion_detection_emits_cv_motion(self, mock_mss_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="motion_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="motion_test")

            config = ScreenConfig(enabled=True, fps_target=30.0)

            runtime = ScreenRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            # Lower motion threshold for test
            runtime._motion_threshold = 0.001

            runtime.start()
            time.sleep(0.5)  # Let capture run more frames
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            motion_events = [e for e in events if e['type'] == 'cv_motion']
            assert len(motion_events) >= 1

            for e in motion_events:
                assert e['session_id'] == 'motion_test'
                assert e['source_lobe'] == 'screen'
                assert 'clock_ns' in e
                assert 'motion' in e['payload']
                assert 0.0 <= e['payload']['motion'] <= 1.0

    @patch('qoresence.lobes.screen.mss.mss', return_value=MockMSS())
    def test_coupling_score_with_controller_provider(self, mock_mss_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="coupling_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="coupling_test")

            config = ScreenConfig(enabled=True, fps_target=30.0)

            runtime = ScreenRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            # Set controller provider that returns varying features
            call_count = [0]

            def controller_provider():
                call_count[0] += 1
                # Simulate trigger press pattern
                return np.array([0.5 + 0.3 * np.sin(call_count[0] * 0.5)])

            runtime.set_controller_provider(controller_provider)

            runtime.start()
            time.sleep(1.0)  # Let coupling buffer fill (need 10+ samples at 30fps)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            coupling_events = [e for e in events if e['type'] == 'coupling_score']
            assert len(coupling_events) >= 1

            for e in coupling_events:
                assert 'coupling_score' in e['payload']
                assert 'negative_control' in e['payload']
                assert 'best_lag_ms' in e['payload']
                assert -1.0 <= e['payload']['coupling_score'] <= 1.0

    @patch('qoresence.lobes.screen.mss.mss', return_value=MockMSS())
    def test_ocr_hud_emits_events(self, mock_mss_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="ocr_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="ocr_test")

            config = ScreenConfig(enabled=True, fps_target=30.0)

            runtime = ScreenRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            # Mock _ocr_hud_regions to return test data
            def mock_ocr(frame):
                return {"scoreboard": "21 - 14", "quarter": "2"}

            runtime._ocr_hud_regions = mock_ocr

            runtime.start()
            time.sleep(0.1)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            ocr_events = [e for e in events if e['type'] == 'ocr_hud']
            assert len(ocr_events) >= 1

            for e in ocr_events:
                assert 'region' in e['payload']
                assert 'text' in e['payload']

    @patch('qoresence.lobes.screen.mss.mss', return_value=MockMSS())
    def test_session_start_and_end_events(self, mock_mss_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="session_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="session_test")

            config = ScreenConfig(enabled=True, fps_target=30.0)

            runtime = ScreenRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.1)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            event_types = [e['type'] for e in events]
            assert 'session_start' in event_types
            assert 'session_end' in event_types

            # Check session_start payload
            start_event = next(e for e in events if e['type'] == 'session_start')
            assert start_event['payload']['capture_fps'] == 30.0

            # Check session_end payload
            end_event = next(e for e in events if e['type'] == 'session_end')
            assert 'frames_captured' in end_event['payload']
            assert end_event['payload']['frames_captured'] > 0


class TestScreenConfigDefaults:
    """Tests for ScreenConfig defaults."""

    def test_defaults(self):
        config = ScreenConfig()
        assert config.enabled is False
        assert config.fps_target == 60.0
        assert config.monitor_index == 0
        assert config.capture_method == "wgc"
        assert config.cv_motion_enabled is True
        assert config.ocr_enabled is False


class TestListMonitors:
    """Test list_monitors helper."""

    @patch('qoresence.lobes.screen.mss.mss')
    def test_lists_monitors(self, mock_mss_class):
        mock_sct = MockMSS()
        mock_mss_class.return_value.__enter__.return_value = mock_sct

        monitors = list_monitors()
        assert len(monitors) >= 1
        assert monitors[0]['index'] == 0
        assert monitors[0]['width'] == 1920
        assert monitors[0]['height'] == 1080


class TestScreenRuntimeIntegration:
    """Integration tests for ScreenRuntime with other lobes."""

    @patch('qoresence.lobes.screen.mss.mss', return_value=MockMSS())
    def test_coupling_with_controller_lobe(self, mock_mss_class):
        """Test coupling analysis with controller lobe features."""
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="integration_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="integration_test")

            config = ScreenConfig(
                enabled=True,
                fps_target=60.0,
            )

            runtime = ScreenRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            # Simulate controller trigger onsets
            trigger_times = []

            def controller_provider():
                now = time.time()
                trigger_times.append(now)
                # Return trigger value (0.0 to 1.0)
                if len(trigger_times) % 10 < 3:
                    return np.array([0.9])  # Trigger pressed
                return np.array([0.0])

            runtime.set_controller_provider(controller_provider)

            runtime.start()
            time.sleep(1.0)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            coupling_events = [e for e in events if e['type'] == 'coupling_score']
            assert len(coupling_events) >= 1

            # Verify coupling score structure
            for e in coupling_events:
                payload = e['payload']
                assert 'coupling_score' in payload
                assert 'negative_control' in payload
                assert 'best_lag_ms' in payload


class TestHUDRegions:
    """Test HUD region definitions."""

    def test_ncaa_regions_defined(self):
        from qoresence.lobes.screen import NCAA_HUD_REGIONS
        assert "scoreboard" in NCAA_HUD_REGIONS
        assert "down_distance" in NCAA_HUD_REGIONS
        assert "play_clock" in NCAA_HUD_REGIONS
        assert "quarter" in NCAA_HUD_REGIONS

        for region, (x, y, w, h) in NCAA_HUD_REGIONS.items():
            assert 0 <= x <= 1
            assert 0 <= y <= 1
            assert 0 < w <= 1
            assert 0 < h <= 1

    def test_cod_regions_defined(self):
        from qoresence.lobes.screen import COD_HUD_REGIONS
        assert "kill_feed" in COD_HUD_REGIONS
        assert "health" in COD_HUD_REGIONS
        assert "ammo" in COD_HUD_REGIONS
        assert "streak" in COD_HUD_REGIONS

        for region, (x, y, w, h) in COD_HUD_REGIONS.items():
            assert 0 <= x <= 1
            assert 0 <= y <= 1
            assert 0 < w <= 1
            assert 0 < h <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])