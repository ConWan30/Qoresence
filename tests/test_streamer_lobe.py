"""
Phase 3 Tests — Streamer Lobe

Synthetic tests using fake capture to verify event emission,
eye-check gate, activity detection, zones, and presence sync.
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
from qoresence.lobes.streamer import StreamerRuntime, ZoneSpec


class FakeCapture:
    """Fake cv2.VideoCapture for testing without hardware.

    Simulates real camera timing by spacing frame reads at the
    requested FPS, so the grabber thread doesn't consume all
    frames before the main loop can process them.
    """

    def __init__(self, frames: list[np.ndarray], fps: float = 30.0):
        self._frames = frames
        self._idx = 0
        self._opened = True
        self._props = {}
        self._fps = fps
        self._last_read_time = 0.0
        self._frame_interval = 1.0 / fps if fps > 0 else 0.0

    def isOpened(self) -> bool:
        return self._opened

    def set(self, prop_id: int, value: float) -> None:
        self._props[prop_id] = value
        # Track FPS changes from the streamer
        if prop_id == 5:  # cv2.CAP_PROP_FPS
            self._fps = max(1.0, value)
            self._frame_interval = 1.0 / self._fps

    def get(self, prop_id: int) -> float:
        return self._props.get(prop_id, 0.0)

    def read(self) -> tuple[bool, np.ndarray | None]:
        # Simulate camera timing — block until next frame interval
        now = time.monotonic()
        if self._last_read_time > 0:
            elapsed = now - self._last_read_time
            if elapsed < self._frame_interval:
                time.sleep(self._frame_interval - elapsed)
        self._last_read_time = time.monotonic()

        if self._idx < len(self._frames):
            frame = self._frames[self._idx]
            self._idx += 1
            return True, frame
        # Loop frames to keep the stream alive
        if self._frames:
            return True, self._frames[-1]
        return False, None

    def release(self) -> None:
        self._opened = False


def _make_test_frames(
    count: int, base_luma: int = 40, motion_frames: list[int] = None
) -> list[np.ndarray]:
    """Create synthetic BGR frames for testing."""
    frames = []
    for i in range(count):
        frame = np.full((240, 320, 3), base_luma, dtype=np.uint8)
        # Add motion to specific frames
        if motion_frames and i in motion_frames:
            # High contrast region for motion detection
            frame[50:100, 50:150] = 200
        frames.append(frame)
    return frames


class TestStreamerRuntime:
    """Tests for StreamerRuntime core functionality."""

    def test_runtime_creation(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="test_session", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="test_session")

            config = StreamerConfig(
                enabled=True,
                device_index=0,
                source_kind="uvc_card",
                eye_check_required=True,
            )

            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            assert runtime.config == config
            assert runtime.session_head_ns == identity.session_head_ns
            assert not runtime.is_running()

    @patch("qoresence.lobes.streamer.cv2.VideoCapture")
    def test_start_opens_capture(self, mock_cap_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="test_session", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="test_session")

            config = StreamerConfig(enabled=True, device_index=0, eye_check_required=False)

            # Create fake frames
            frames = _make_test_frames(10)
            fake_cap = FakeCapture(frames)
            mock_cap_class.return_value = fake_cap

            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            assert runtime.start() is True
            assert runtime.is_running()

            runtime.stop()

    @patch("qoresence.lobes.streamer.cv2.VideoCapture")
    def test_eye_check_snapshot_saved(self, mock_cap_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="eye_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="eye_test")

            config = StreamerConfig(
                enabled=True,
                device_index=0,
                eye_check_required=True,
                snapshot_path=str(Path(td) / "eye_check.png"),
            )

            frames = _make_test_frames(5)
            fake_cap = FakeCapture(frames)
            mock_cap_class.return_value = fake_cap

            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.1)  # Let it process a few frames
            runtime.stop()

            # Check eye-check snapshot was saved
            snap_path = Path(td) / "eye_check.png"
            assert snap_path.exists(), "Eye-check snapshot not saved"

    @patch("qoresence.lobes.streamer.cv2.VideoCapture")
    def test_activity_detection_emits_events(self, mock_cap_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="activity_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="activity_test")

            config = StreamerConfig(
                enabled=True,
                device_index=0,
                motion_high=10.0,
                motion_low=2.0,
                activity_hysteresis_s=0.0,  # Instant transition for test
                stats_every_s=999.0,  # Disable periodic stats
                heartbeat_every_s=999.0,
                eye_check_required=False,
            )

            # Frames: idle -> high motion -> idle
            frames = _make_test_frames(
                6,
                base_luma=40,
                motion_frames=[2, 3],  # Frames 2,3 have high motion
            )
            fake_cap = FakeCapture(frames)
            mock_cap_class.return_value = fake_cap

            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.5)  # Let loop run
            runtime.stop()

            # Check events emitted
            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]  # JSONL lines

            # Should have session_start, activity transitions, session_end
            event_types = [e["type"] for e in events]
            assert "session_start" in event_types
            assert "session_end" in event_types
            assert "activity" in event_types

            # Check activity events have required fields
            activity_events = [e for e in events if e["type"] == "activity"]
            for ae in activity_events:
                assert ae["session_id"] == "activity_test"
                assert ae["source_lobe"] == "streamer"
                assert "clock_ns" in ae
                assert "session_head_ns" in ae
                assert "payload" in ae
                assert "level" in ae["payload"]
                assert "presence_sync_ok" in ae["payload"]

    @patch("qoresence.lobes.streamer.cv2.VideoCapture")
    def test_zone_detection_emits_events(self, mock_cap_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="zone_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="zone_test")

            config = StreamerConfig(
                enabled=True,
                device_index=0,
                zones_enabled=True,
                stats_every_s=999.0,
                heartbeat_every_s=999.0,
                eye_check_required=False,
            )

            # Frame with zone activity (scoreboard region bright)
            frames = _make_test_frames(3, base_luma=30)
            # Make scoreboard zone bright in frame 1
            frames[1][20:50, 80:240] = 220  # Matches hud_scoreboard zone roughly

            fake_cap = FakeCapture(frames)
            mock_cap_class.return_value = fake_cap

            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.3)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]

            zone_events = [e for e in events if e["type"] == "zone"]
            assert len(zone_events) > 0, "No zone events emitted"

            for ze in zone_events:
                assert ze["source_lobe"] == "streamer"
                assert "zone_id" in ze["payload"]
                assert "state" in ze["payload"]
                assert "presence_sync_ok" in ze["payload"]

    @patch("qoresence.lobes.streamer.cv2.VideoCapture")
    def test_frame_stats_periodic(self, mock_cap_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="stats_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="stats_test")

            config = StreamerConfig(
                enabled=True,
                device_index=0,
                stats_every_s=0.1,  # Frequent stats for test
                heartbeat_every_s=999.0,
                eye_check_required=False,
            )

            frames = _make_test_frames(20)
            fake_cap = FakeCapture(frames)
            mock_cap_class.return_value = fake_cap

            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            runtime.start()
            time.sleep(0.5)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]

            frame_stats = [e for e in events if e["type"] == "frame_stats"]
            assert len(frame_stats) >= 2, "Expected multiple frame_stats events"

            for fs in frame_stats:
                assert "n" in fs["payload"]
                assert "fps_meas" in fs["payload"]
                assert "presence_sync_ok" in fs["payload"]


class TestPresenceSync:
    """Tests for presence synchronization via touch file."""

    @patch("qoresence.lobes.streamer.cv2.VideoCapture")
    def test_presence_sync_true_when_touch_recent(self, mock_cap_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="presence_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="presence_test")

            touch_file = Path(td) / "presence.touch"
            touch_file.write_text("touch")

            config = StreamerConfig(
                enabled=True,
                device_index=0,
                stats_every_s=0.05,
                heartbeat_every_s=999.0,
                eye_check_required=False,
            )

            frames = _make_test_frames(10, motion_frames=[1, 2, 3])
            fake_cap = FakeCapture(frames)
            mock_cap_class.return_value = fake_cap

            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
                presence_touch_file=touch_file,
                presence_timeout_s=5.0,
            )

            runtime.start()
            time.sleep(0.3)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]

            # Check activity/frame_stats have presence_sync_ok = true
            for e in events:
                if e["type"] in ("activity", "frame_stats", "zone"):
                    assert e["payload"]["presence_sync_ok"] is True, (
                        f"Expected presence_sync_ok=true for {e['type']}"
                    )

    @patch("qoresence.lobes.streamer.cv2.VideoCapture")
    def test_presence_sync_false_when_touch_stale(self, mock_cap_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(
                session_id="presence_stale", jsonl_path=jsonl_path, enable_ws=False
            )
            identity = SessionAuthority.mint(session_id="presence_stale")

            touch_file = Path(td) / "presence.touch"
            touch_file.write_text("touch")
            # Make it stale by setting mtime to 100 seconds ago
            import os

            stale_time = time.time() - 100
            os.utime(touch_file, (stale_time, stale_time))

            config = StreamerConfig(
                enabled=True,
                device_index=0,
                stats_every_s=0.05,
                heartbeat_every_s=999.0,
                eye_check_required=False,
            )

            frames = _make_test_frames(10, motion_frames=[1, 2, 3])
            fake_cap = FakeCapture(frames)
            mock_cap_class.return_value = fake_cap

            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
                presence_touch_file=touch_file,
                presence_timeout_s=5.0,
            )

            runtime.start()
            time.sleep(0.3)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]

            for e in events:
                if e["type"] in ("activity", "frame_stats", "zone"):
                    assert e["payload"]["presence_sync_ok"] is False, (
                        f"Expected presence_sync_ok=false for {e['type']} (stale touch)"
                    )

    @patch("qoresence.lobes.streamer.cv2.VideoCapture")
    def test_presence_sync_false_when_no_touch_file(self, mock_cap_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="presence_none", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="presence_none")

            config = StreamerConfig(
                enabled=True,
                device_index=0,
                stats_every_s=0.05,
                heartbeat_every_s=999.0,
                eye_check_required=False,
            )

            frames = _make_test_frames(10, motion_frames=[1, 2, 3])
            fake_cap = FakeCapture(frames)
            mock_cap_class.return_value = fake_cap

            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
                presence_touch_file=Path(td) / "nonexistent.touch",
                presence_timeout_s=5.0,
            )

            runtime.start()
            time.sleep(0.3)
            runtime.stop()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]

            for e in events:
                if e["type"] in ("activity", "frame_stats", "zone"):
                    assert e["payload"]["presence_sync_ok"] is False


class TestZoneSpec:
    """Tests for ZoneSpec configuration."""

    def test_default_zones_defined(self):
        from qoresence.lobes.streamer import DEFAULT_ZONES

        assert len(DEFAULT_ZONES) == 2
        assert DEFAULT_ZONES[0].zone_id == "hud_scoreboard"
        assert DEFAULT_ZONES[1].zone_id == "hud_bottom"

    def test_zone_coordinates_normalized(self):
        zone = ZoneSpec("test", 0.1, 0.2, 0.3, 0.4)
        assert zone.x == 0.1
        assert zone.y == 0.2
        assert zone.width == 0.3
        assert zone.height == 0.4


class TestStreamerConfigDefaults:
    """Tests for StreamerConfig defaults."""

    def test_defaults(self):
        config = StreamerConfig()
        assert config.enabled is False
        assert config.device_index == 0
        assert config.source_kind == "uvc_card"
        assert config.width == 1280
        assert config.height == 720
        assert config.fps_target == 15.0
        assert config.eye_check_required is True
        assert config.zones_enabled is True


class TestStreamerHardening:
    """Tests for Phase 5 streamer hardening: watchdog heartbeat + FPS fallback."""

    @patch("qoresence.lobes.streamer.cv2.VideoCapture")
    def test_watchdog_emits_heartbeat_when_capture_stalls(self, mock_cap_class):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="watchdog_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="watchdog_test")

            # Single frame: _open_capture consumes it, then capture stalls
            frames = _make_test_frames(1)
            fake_cap = FakeCapture(frames)
            mock_cap_class.return_value = fake_cap

            config = StreamerConfig(
                enabled=True,
                device_index=0,
                fps_target=30.0,
                eye_check_required=False,
                stats_every_s=60.0,  # avoid periodic stats/heartbeat from _run_loop
                heartbeat_every_s=60.0,
            )
            runtime = StreamerRuntime(
                config=config,
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )

            assert runtime.start() is True
            time.sleep(1.2)
            runtime.stop()

            # Parse JSONL and look for heartbeat events (BaseEvent serializes as "type")
            events = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
            heartbeats = [json.loads(line) for line in events if line.strip()]
            heartbeats = [e for e in heartbeats if e.get("type") == "heartbeat"]
            assert len(heartbeats) >= 1, "watchdog should emit at least one heartbeat while stalled"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
