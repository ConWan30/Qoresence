"""
Phase 9 Tests — OBS Overlay Integration

Tests for OBS Browser Source overlay integration with Qoresence event bus.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from qoresence.core import (
    RetinaEventBus,
    SessionAuthority,
    StreamerConfig,
)
from qoresence.lobes.streamer import StreamerRuntime


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

    @patch(
        "qoresence.lobes.streamer.list_dshow_devices",
        return_value=[(0, "USB3.0 Video", True, "dshow")],
    )
    @patch("qoresence.lobes.streamer._get_dshow_device_name", return_value="USB3.0 Video")
    @patch("qoresence.lobes.streamer.cv2.VideoCapture")
    def test_streamer_emits_events_for_overlay(self, mock_cv2_class, _name, _devs):
        """Test that streamer emits events that overlay can consume."""
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="overlay_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="overlay_test")

            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            mock_cap = mock_cv2_class.return_value
            mock_cap.isOpened.return_value = True
            mock_cap.get.return_value = 30.0
            read_count = [0]

            def mock_read():
                read_count[0] += 1
                if read_count[0] <= 8:
                    return True, frame
                return False, None

            mock_cap.read.side_effect = mock_read

            config = StreamerConfig(
                enabled=True,
                device_index=0,
                device_name="USB3.0 Video",
                source_kind="uvc_card",
                width=640,
                height=480,
                fps_target=30.0,
                eye_check_required=True,
                snapshot_path=str(Path(td) / "eye_check.png"),
                enable_ws=False,
                zones_enabled=True,
                presence_touch_file=None,
            )

            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.5)
            runtime.stop()

            assert jsonl_path.exists(), (
                f"streamer wrote no JSONL rejected={bus.events_rejected} "
                f"emitted={bus.events_emitted}"
            )
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

            bus.close()


class TestOBSOverlayHealthCheck:
    """Tests for health check integration."""

    def test_health_check_includes_overlay_status(self):
        """Test that health checks can include overlay status."""
        # This would be implemented when the health check endpoint is added
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
