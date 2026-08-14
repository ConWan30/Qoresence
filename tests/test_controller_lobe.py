"""
Phase 4 Tests — Controller Lobe

Synthetic tests using fake HID device to verify event emission,
rolling buffer, causal_parent_ns, trigger onset detection, stick motion.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from qoresence.core import (
    ControllerConfig,
    EventType,
    RetinaEventBus,
    SessionAuthority,
    SourceLobe,
)
from qoresence.lobes.controller import ControllerRuntime, get_controller_runtime, list_controllers


class FakeHIDDevice:
    """Fake hid.Device for testing without hardware.

    Mimics the hidapi device API: instantiate, then call open() or open_path(),
    then read(max_length, timeout_ms).
    """

    def __init__(self, reports: list[bytes]):
        self._reports = reports
        self._idx = 0
        self._closed = False
        self._opened = False

    def open(
        self, vendor_id: int = 0, product_id: int = 0, serial_number: str | None = None
    ) -> None:
        self._opened = True

    def open_path(self, path: bytes) -> None:
        self._opened = True

    def read(self, max_length: int, timeout_ms: int = 0) -> list[int] | None:
        if self._closed or not self._opened or self._idx >= len(self._reports):
            return None
        report = self._reports[self._idx]
        self._idx += 1
        return list(report)

    def close(self) -> None:
        self._closed = True

    def set_nonblocking(self, v: int) -> None:
        pass


def _make_dualsense_report(
    buttons: int = 0,
    l2: int = 0,
    r2: int = 0,
    lx: int = 128,
    ly: int = 128,
    rx: int = 128,
    ry: int = 128,
    gyro: tuple[int, int, int] = (0, 0, 0),
    accel: tuple[int, int, int] = (0, 0, 0),
    battery: int = 100,
    usb_state: int = 1,
) -> bytes:
    """Create a synthetic DualSense USB 0x01 report (canonical offsets)."""
    from qoresence.sync.hid_report import pack_usb_report

    return pack_usb_report(
        buttons=buttons,
        l2=l2,
        r2=r2,
        lx=lx,
        ly=ly,
        rx=rx,
        ry=ry,
        gyro=gyro,
        accel=accel,
    )


class TestControllerRuntime:
    """Tests for ControllerRuntime core functionality."""

    def test_runtime_creation(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="test_session", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="test_session")

            config = ControllerConfig(enabled=True)

            runtime = ControllerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            assert runtime.config == config
            assert runtime.session_head_ns == identity.session_head_ns
            assert not runtime.is_running()

    @patch("qoresence.lobes.controller.HIDDevice")
    def test_start_opens_device(self, mock_device_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="test_session", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="test_session")

            config = ControllerConfig(enabled=True, device_vid=0x054C, device_pid=0x0CE6)

            # Create fake reports
            reports = [_make_dualsense_report() for _ in range(10)]
            fake_device = FakeHIDDevice(reports)
            mock_device_class.return_value = fake_device

            runtime = ControllerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            assert runtime.start() is True
            assert runtime.is_running()
            assert runtime.get_stats()["connected"] is True
            assert get_controller_runtime() is runtime

            runtime.stop()
            assert get_controller_runtime() is None

    @patch("qoresence.lobes.controller.HIDDevice")
    def test_button_press_emits_events(self, mock_device_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="button_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="button_test")

            config = ControllerConfig(enabled=True, poll_rate_hz=1000.0)

            # Report 1: no buttons
            # Report 2: CROSS pressed (bit 0)
            # Report 3: CROSS released
            reports = [
                _make_dualsense_report(buttons=0),
                _make_dualsense_report(buttons=1),  # CROSS
                _make_dualsense_report(buttons=0),
            ]
            fake_device = FakeHIDDevice(reports)
            mock_device_class.return_value = fake_device

            runtime = ControllerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.1)  # Let loop process
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]

            # Check for controller_event with button press/release
            controller_events = [e for e in events if e["type"] == "controller_event"]
            button_events = [e for e in controller_events if "button" in e["payload"]]

            press_events = [e for e in button_events if e["payload"].get("action") == "press"]
            release_events = [e for e in button_events if e["payload"].get("action") == "release"]

            assert len(press_events) >= 1, "Expected button press event"
            assert len(release_events) >= 1, "Expected button release event"

            for e in press_events + release_events:
                assert e["session_id"] == "button_test"
                assert e["source_lobe"] == "controller"
                assert "clock_ns" in e
                assert "session_head_ns" in e
                assert "causal_parent_ns" in e["payload"]

    @patch("qoresence.lobes.controller.HIDDevice")
    def test_trigger_onset_detection(self, mock_device_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="trigger_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="trigger_test")

            config = ControllerConfig(enabled=True, poll_rate_hz=1000.0)

            # R2 goes from 0 -> 200 (past threshold ~30)
            reports = [
                _make_dualsense_report(r2=0),
                _make_dualsense_report(r2=10),
                _make_dualsense_report(r2=50),  # Onset here
                _make_dualsense_report(r2=200),
                _make_dualsense_report(r2=200),
                _make_dualsense_report(r2=0),
            ]
            fake_device = FakeHIDDevice(reports)
            mock_device_class.return_value = fake_device

            runtime = ControllerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.1)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]

            trigger_events = [e for e in events if e["type"] == "trigger_onset"]
            r2_events = [e for e in trigger_events if e["payload"]["trigger"] == "R2"]

            assert len(r2_events) == 1, f"Expected exactly one R2 onset, got {len(r2_events)}"
            assert r2_events[0]["payload"]["amplitude"] > 0.1
            assert "causal_parent_ns" in r2_events[0]["payload"]

    @patch("qoresence.lobes.controller.HIDDevice")
    def test_stick_motion_detection(self, mock_device_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="stick_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="stick_test")

            config = ControllerConfig(enabled=True, poll_rate_hz=1000.0)

            # Left stick moves from center (128,128) to (200, 128)
            reports = [
                _make_dualsense_report(lx=128, ly=128),
                _make_dualsense_report(lx=130, ly=128),  # Small - within deadzone
                _make_dualsense_report(lx=150, ly=128),  # Past deadzone (15)
                _make_dualsense_report(lx=200, ly=128),
                _make_dualsense_report(lx=128, ly=128),  # Back to center
            ]
            fake_device = FakeHIDDevice(reports)
            mock_device_class.return_value = fake_device

            runtime = ControllerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.1)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]

            stick_events = [e for e in events if e["type"] == "stick_motion"]
            left_stick = [e for e in stick_events if e["payload"]["stick"] == "left"]

            assert len(left_stick) >= 1, "Expected left stick motion event"
            for e in left_stick:
                assert "x" in e["payload"]
                assert "y" in e["payload"]
                assert "causal_parent_ns" in e["payload"]

    @patch("qoresence.lobes.controller.HIDDevice")
    def test_imu_tremor_sample(self, mock_device_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="imu_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="imu_test")

            config = ControllerConfig(enabled=True, poll_rate_hz=1000.0)

            # Reports with IMU data
            reports = [
                _make_dualsense_report(gyro=(100, -50, 200), accel=(1000, -200, 9800)),
                _make_dualsense_report(gyro=(110, -55, 210), accel=(1010, -210, 9810)),
            ]
            fake_device = FakeHIDDevice(reports)
            mock_device_class.return_value = fake_device

            runtime = ControllerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.1)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]

            tremor_events = [e for e in events if e["type"] == "tremor_sample"]
            assert len(tremor_events) >= 1, "Expected tremor_sample event"

            for e in tremor_events:
                assert "gyro" in e["payload"]
                assert "accel" in e["payload"]
                assert len(e["payload"]["gyro"]) == 3
                assert len(e["payload"]["accel"]) == 3
                assert "causal_parent_ns" in e["payload"]

    @patch("qoresence.lobes.controller.HIDDevice")
    def test_rolling_buffer_populated(self, mock_device_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="buffer_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="buffer_test")

            config = ControllerConfig(enabled=True, buffer_size=100)

            reports = [_make_dualsense_report() for _ in range(10)]
            fake_device = FakeHIDDevice(reports)
            mock_device_class.return_value = fake_device

            runtime = ControllerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.1)
            runtime.stop()

            # Check buffer
            buffer = runtime.get_buffer_snapshot()
            assert len(buffer) > 0, "Buffer should have entries"
            assert len(buffer) <= config.buffer_size

            for entry in buffer:
                assert entry.clock_ns > 0
                assert entry.source_lobe == SourceLobe.CONTROLLER
                assert isinstance(entry.event_type, EventType)
                assert isinstance(entry.payload, dict)

    @patch("qoresence.lobes.controller.HIDDevice")
    def test_causal_parent_ns_in_events(self, mock_device_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="causal_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="causal_test")

            config = ControllerConfig(enabled=True, poll_rate_hz=1000.0)

            # Two rapid button presses
            reports = [
                _make_dualsense_report(buttons=0),
                _make_dualsense_report(buttons=1),  # CROSS press
                _make_dualsense_report(buttons=0),
                _make_dualsense_report(buttons=2),  # CIRCLE press
                _make_dualsense_report(buttons=0),
            ]
            fake_device = FakeHIDDevice(reports)
            mock_device_class.return_value = fake_device

            runtime = ControllerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.1)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]

            button_events = [
                e for e in events if e["type"] == "controller_event" and "button" in e["payload"]
            ]

            # Second press should have causal_parent_ns pointing to first press
            for e in button_events:
                if e["payload"].get("action") == "press":
                    parent = e["payload"].get("causal_parent_ns")
                    if parent is not None:
                        assert parent > 0
                        assert parent <= e["clock_ns"]  # Can be equal due to time resolution


class TestControllerConfigDefaults:
    """Tests for ControllerConfig defaults."""

    def test_defaults(self):
        config = ControllerConfig()
        assert config.enabled is False
        assert config.device_vid is None
        assert config.device_pid is None
        assert config.poll_rate_hz == 1000.0
        assert config.buffer_size == 1000
        assert config.causal_parent_ns_enabled is True


class TestListControllers:
    """Test list_controllers helper."""

    @patch("qoresence.lobes.controller.hid.enumerate")
    def test_lists_sony_controller(self, mock_enumerate):
        mock_enumerate.return_value = [
            {
                "vendor_id": 0x054C,
                "product_id": 0x0CE6,
                "path": b"/dev/hidraw0",
                "product_string": "DualSense Edge",
                "manufacturer_string": "Sony Interactive Entertainment",
            },
            {
                "vendor_id": 0x046D,
                "product_id": 0xC077,
                "path": b"/dev/hidraw1",
                "product_string": "G502 Mouse",
                "manufacturer_string": "Logitech",
            },  # Not a controller
        ]

        controllers = list_controllers()
        assert len(controllers) == 1
        assert controllers[0]["vid"] == 0x054C
        assert controllers[0]["pid"] == 0x0CE6
        assert "DualSense" in controllers[0]["product"]


class TestHotPlugAndFixture:
    """Waiting mode + software DualSense through ingest_report."""

    @patch("qoresence.lobes.controller.list_controllers", return_value=[])
    @patch("qoresence.lobes.controller.HIDDevice")
    def test_start_without_device_waits(self, mock_device_class, _mock_list):
        fake = FakeHIDDevice([])
        fake.open = lambda *a, **k: (_ for _ in ()).throw(OSError("no pad"))
        fake.open_path = lambda *a, **k: (_ for _ in ()).throw(OSError("no pad"))
        mock_device_class.return_value = fake

        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="wait_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="wait_test")
            runtime = ControllerRuntime(
                config=ControllerConfig(enabled=True),
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )
            assert runtime.start() is True
            assert runtime.is_running()
            stats = runtime.get_stats()
            assert stats["connected"] is False
            assert stats["waiting"] is True
            runtime.stop()

    def test_fixture_bodied_r2_binds_score(self):
        from qoresence.sync.dualsense_fixture import feed_bodied_r2

        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="fix_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="fix_test")
            runtime = ControllerRuntime(
                config=ControllerConfig(enabled=True),
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )
            out = feed_bodied_r2(runtime)
            assert out["ok"] is True
            assert out["last_bind"]["mode"] == "TEMPORAL"
            assert out["last_bind"]["visual_kind"] == "score_changed"
            assert out["last_bind"]["hid_name"] in {"R2", "r2_btn"}
            assert out["imu_bodied"] is True
            assert runtime.get_stats()["reports"] >= 4

    @patch("qoresence.lobes.controller.HIDDevice")
    def test_reconnect_after_drop(self, mock_device_class):
        reports = [_make_dualsense_report() for _ in range(30)]
        fake = FakeHIDDevice(reports)
        mock_device_class.return_value = fake
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="re_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="re_test")
            runtime = ControllerRuntime(
                config=ControllerConfig(enabled=True, device_vid=0x054C, device_pid=0x0CE6),
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )
            runtime._reconnect_s = 0.05
            assert runtime.start() is True
            time.sleep(0.05)
            assert runtime.get_stats()["connected"] is True
            runtime._drop_device()
            assert runtime.get_stats()["connected"] is False
            time.sleep(0.2)
            assert runtime.get_stats()["connected"] is True
            runtime.stop()


class TestPresenceTouchFile:
    """Test presence touch file creation."""

    @patch("qoresence.lobes.controller.HIDDevice")
    def test_touch_file_created_on_input(self, mock_device_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="touch_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="touch_test")

            touch_file = Path(td) / "controller.touch"

            config = ControllerConfig(enabled=True)

            reports = [
                _make_dualsense_report(buttons=0),
                _make_dualsense_report(buttons=1),  # Button press
                _make_dualsense_report(r2=100),  # Trigger
            ]
            fake_device = FakeHIDDevice(reports)
            mock_device_class.return_value = fake_device

            runtime = ControllerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
                presence_touch_file=touch_file,
            )

            runtime.start()
            time.sleep(0.1)
            runtime.stop()

            # Touch file should exist and have recent mtime
            assert touch_file.exists()
            assert time.time() - touch_file.stat().st_mtime < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
