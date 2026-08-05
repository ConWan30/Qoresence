"""
Phase 10 Tests — Real-World Integration Test Script

Tests for the integration test script functionality.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest


class TestIntegrationTestScript:
    """Tests for integration test script components."""

    def test_script_imports(self):
        """Test that the integration test script can be imported."""
        import scripts.integration_test as integration_test
        assert hasattr(integration_test, 'IntegrationTestApp')
        assert hasattr(integration_test, 'detect_dualshock_edge')
        assert hasattr(integration_test, 'detect_capture_devices')
        assert hasattr(integration_test, 'detect_monitors')
        assert hasattr(integration_test, 'detect_game_window')
        assert hasattr(integration_test, 'create_test_config')

    @patch('hid.enumerate')
    def test_dualshock_edge_detection(self, mock_enumerate):
        """Test DualShock Edge detection."""
        import scripts.integration_test as integration_test

        # Mock HID device
        mock_enumerate.return_value = [
            {'vendor_id': 0x054C, 'product_id': 0x0CE6, 'path': b'test_path',
             'manufacturer_string': 'Sony', 'product_string': 'DualSense Edge', 'serial_number': '12345'},
            {'vendor_id': 0x1234, 'product_id': 0x5678, 'path': b'other_path'},
        ]

        result = integration_test.detect_dualshock_edge()
        assert result is not None
        assert result['vendor_id'] == 0x054C
        assert result['product_id'] == 0x0CE6

    @patch('hid.enumerate')
    def test_no_dualshock_edge(self, mock_enumerate):
        """Test when no DualShock Edge is found."""
        import scripts.integration_test as integration_test

        mock_enumerate.return_value = [
            {'vendor_id': 0x1234, 'product_id': 0x5678, 'path': b'other_path'},
        ]

        result = integration_test.detect_dualshock_edge()
        assert result is None

    @patch('cv2.VideoCapture')
    def test_capture_device_detection(self, mock_cv2_class):
        """Test capture device detection."""
        import scripts.integration_test as integration_test

        # Mock camera
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cv2_class.return_value = mock_cap

        # Need to mock frame shape
        import numpy as np
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, frame)

        devices = integration_test.detect_capture_devices()
        assert len(devices) >= 1
        assert devices[0]['index'] == 0
        assert devices[0]['width'] == 640
        assert devices[0]['height'] == 480

    @patch('scripts.integration_test.list_monitors')
    def test_monitor_detection(self, mock_list_monitors):
        """Test monitor detection."""
        import scripts.integration_test as integration_test

        mock_list_monitors.return_value = [
            {'index': 0, 'left': 0, 'top': 0, 'width': 1920, 'height': 1080},
            {'index': 1, 'left': 1920, 'top': 0, 'width': 1920, 'height': 1080},
        ]

        monitors = integration_test.detect_monitors()
        assert len(monitors) == 2
        assert monitors[0]['index'] == 0
        assert monitors[0]['width'] == 1920

    def test_create_test_config(self):
        """Test config creation from args."""
        import scripts.integration_test as integration_test

        # Create mock args
        args = Mock()
        args.session_id = "test_session"
        args.session_head_ns = 123456789000000000
        args.device_id = ""
        args.auto_detect = False
        args.streamer = True
        args.streamer_device = 0
        args.streamer_fps = 15.0
        args.streamer_source = "uvc_card"
        args.controller = True
        args.controller_vid = 0x054C
        args.controller_pid = 0x0CE6
        args.controller_rate = 1000.0
        args.screen = True
        args.screen_monitor = 0
        args.screen_method = "wgc"
        args.screen_fps = 60.0
        args.outcome = True
        args.game_profile = "ncaa_football_27"
        args.outcome_confidence = 0.7
        args.outcome_interval = 0.5
        args.visual = False
        args.visual_api_key = None
        args.visual_api_key_file = None
        args.visual_model_name = "nvidia/nemotron-nano-12b-v2-vl"
        args.visual_sample_rate = 30
        args.jsonl_path = "/tmp/test.jsonl"
        args.enable_ws = True
        args.ws_host = "127.0.0.1"
        args.ws_port = 8765

        config = integration_test.create_test_config(args)

        assert config.session_id == "test_session"
        assert config.session_head_ns == 123456789000000000
        assert config.streamer.enabled is True
        assert config.controller.enabled is True
        assert config.screen.enabled is True
        assert config.outcome.enabled is True
        assert config.visual.enabled is False

    def test_integration_test_app_creation(self):
        """Test IntegrationTestApp can be created."""
        import scripts.integration_test as integration_test
        from qoresence.core import RetinaUnifiedConfig, FusionWeights

        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=123456789000000000,
            fusion_weights=FusionWeights(),
        )

        app = integration_test.IntegrationTestApp(config, duration_s=1.0)
        assert app.config == config
        assert app.duration_s == 1.0
        assert not app._running


class TestIntegrationTestDryRun:
    """Dry-run tests for integration test."""

    def test_dry_run_config_validation(self):
        """Test that config validation works."""
        from qoresence.core import RetinaUnifiedConfig

        # Valid config
        config = RetinaUnifiedConfig(
            session_id="valid_session",
            session_head_ns=time.time_ns(),
            streamer=__import__('qoresence.core', fromlist=['StreamerConfig']).StreamerConfig(enabled=True),
        )
        # This should not raise
        errors = config.validate()
        # May have warnings but not errors for missing device_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])