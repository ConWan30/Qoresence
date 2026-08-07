"""
Phase 9 Tests — OBS Overlay Integration

Tests for OBS Browser Source overlay integration with Qoresence event bus.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from qoresence.core import (
    RetinaEventBus,
    SessionAuthority,
)
from qoresence.lobes import StreamerRuntime


class TestOBSOverlayIntegration:
    """Tests for OBS overlay integration with event bus."""

    def test_overlay_file_exists(self):
        """Test that the OBS overlay HTML file exists."""
        overlay_path = Path("tools/obs/presence_overlay.html")
        assert overlay_path.exists(), f"Overlay file not found at {overlay_path}"

    def test_overlay_contains_required_elements(self):
        """Test that the overlay contains required HTML elements."""
        overlay_path = Path("tools/obs/presence_overlay.html")
        content = overlay_path.read_text(encoding="utf-8")

        # Check for key element IDs (actual overlay uses these IDs)
        assert "wsStatus" in content, "Missing wsStatus element"
        assert "sessionId" in content, "Missing sessionId element"
        assert "sourceKind" in content, "Missing sourceKind element"
        assert "frameCount" in content, "Missing frameCount element"
        assert "fpsMeas" in content, "Missing fpsMeas element"
        assert "activityStatus" in content, "Missing activityStatus element"
        assert "activityLevel" in content, "Missing activityLevel element"
        assert "motionVal" in content, "Missing motionVal element"
        assert "lumaVal" in content, "Missing lumaVal element"
        assert "activityFill" in content, "Missing activityFill element"
        assert "presenceStatus" in content, "Missing presenceStatus element"
        assert "presenceSync" in content, "Missing presenceSync element"
        assert "lastInput" in content, "Missing lastInput element"
        assert "zoneList" in content, "Missing zoneList element"
        assert "WebSocket" in content, "Missing WebSocket connection code"

    def test_overlay_handles_streamer_events(self):
        """Test that the overlay handles streamer lobe events."""
        overlay_path = Path("tools/obs/presence_overlay.html")
        content = overlay_path.read_text(encoding="utf-8")

        # Check for event handling
        assert "session_start" in content, "Missing session_start handling"
        assert "frame_stats" in content, "Missing frame_stats handling"
        assert "activity" in content, "Missing activity handling"
        assert "zone" in content, "Missing zone handling"
        assert "heartbeat" in content, "Missing heartbeat handling"
        assert "session_end" in content, "Missing session_end handling"

    def test_overlay_updates_ui_from_events(self):
        """Test that the overlay updates UI from events."""
        overlay_path = Path("tools/obs/presence_overlay.html")
        content = overlay_path.read_text(encoding="utf-8")

        # Check for UI update functions (actual overlay uses these)
        assert "handleEvent" in content, "Missing handleEvent function"
        assert "updateZone" in content, "Missing updateZone function"
        assert "connect" in content, "Missing connect function"

    def test_overlay_handles_websocket_reconnect(self):
        """Test that the overlay handles WebSocket reconnection."""
        overlay_path = Path("tools/obs/presence_overlay.html")
        content = overlay_path.read_text(encoding="utf-8")

        # Check for reconnection logic
        assert "reconnect" in content.lower(), "Missing reconnection logic"
        assert "onclose" in content, "Missing WebSocket onclose handler"
        assert "onerror" in content, "Missing WebSocket onerror handler"
        assert "setTimeout(connect" in content, "Missing reconnection timer"

    def test_overlay_contains_disclaimer(self):
        """Test that the overlay contains the required disclaimer."""
        overlay_path = Path("tools/obs/presence_overlay.html")
        content = overlay_path.read_text(encoding="utf-8")

        assert "Observation plane only" in content, "Missing disclaimer"
        assert "not humanity proof" in content, "Missing disclaimer text"
        assert "not eligibility" in content, "Missing disclaimer text"
        assert "not anti-cheat" in content, "Missing disclaimer text"

    @patch("qoresence.lobes.streamer.cv2.VideoCapture")
    def test_streamer_emits_events_for_overlay(self, mock_cv2_class):
        """Test that streamer emits events that overlay can consume."""
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="overlay_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="overlay_test")

            # Mock camera
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_cap.get.return_value = 30.0
            mock_cap.read.return_value = (True, Mock())
            mock_cv2_class.return_value = mock_cap

            # Create a simple frame
            import numpy as np

            frame = np.zeros((480, 640, 3), dtype=np.uint8)

            read_count = [0]

            def mock_read():
                read_count[0] += 1
                if read_count[0] <= 3:
                    return True, frame
                return False, None

            mock_cap.read.side_effect = mock_read

            config = Mock()
            config.device_index = 0
            config.backend = "auto"
            config.width = 640
            config.height = 480
            config.fps_target = 30.0
            config.process_scale = 0.5
            config.motion_low = 5.0
            config.motion_high = 15.0
            config.activity_hysteresis_s = 0.5
            config.stats_every_s = 1.0
            config.heartbeat_every_s = 5.0
            config.zones_enabled = True
            config.eye_check_required = True
            config.snapshot_path = None
            config.source_kind = "uvc_card"
            config.device_name = "Test Camera"
            config.enable_ws = False
            config.ws_port = 8765
            config.presence_touch_file = None
            config.presence_timeout_s = 5.0

            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.2)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines if line.strip()]

            # Check for events that overlay needs
            event_types = [e["type"] for e in events]
            assert "session_start" in event_types
            assert "activity" in event_types or "frame_stats" in event_types
            assert "session_end" in event_types

            # Verify event structure for overlay
            for e in events:
                assert "session_id" in e
                assert "source_lobe" in e
                assert "clock_ns" in e
                assert "payload" in e


class TestOBSOverlayHealthCheck:
    """Tests for health check integration."""

    def test_health_check_includes_overlay_status(self):
        """Test that health checks can include overlay status."""
        # This would be implemented when the health check endpoint is added
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
