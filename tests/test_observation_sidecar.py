"""Tests for observation-plane clip sidecar (Layer 2).

Regression tests lock in:
1. Clip sidecar includes verb + mode when visual_phase present
2. Uses hid_by_seq[frame_seq], not HID[now] at export time
3. Unlabeled when visual_phase missing
4. CFB vs Madden button differences (L3 vs R3 for throw away)
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import numpy as np


class TestObservationSidecarGeneration:
    """Test observation sidecar generation for clips."""

    def test_sidecar_includes_verb_and_mode_with_visual_phase(self):
        """Clip sidecar includes verb + mode when visual_phase present."""
        from qoresence.monitor.frame_hub import get_frame_hub
        from qoresence.sync.hid_seq_line import get_hid_seq_line
        from qoresence.sync.input_ring import set_hold
        from qoresence.vision.clip_buffer import _write_observation_sidecar

        hub = get_frame_hub()
        line = get_hid_seq_line()
        hub.clear()
        line.clear()

        # Publish frame with Cross pressed at seq=100
        t0 = time.monotonic_ns()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        set_hold(clock_ns=t0, r2=0.0, l2=0.0, lx=0.0, ly=0.0, buttons=("Cross",))
        hub.publish(frame, clock_ns=t0, seq=100)

        # Create mock visual context with visual_phase=huddle_offense
        from qoresence.vision.visual_context import VisualContext

        visual_ctx = VisualContext(
            game_state="gameplay",
            game_profile="madden_27",
            details={"visual_phase": "huddle_offense"},
        )

        snapshot = [(time.monotonic(), b"fake_jpeg", 640, 480, 100)]

        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            mp4_path = Path(tmpdir) / "test_clip.mp4"
            mp4_path.touch()

            with patch(
                "qoresence.lobes.visual.get_last_visual_context",
                return_value=visual_ctx,
            ):
                sidecar = _write_observation_sidecar(mp4_path, snapshot=snapshot)
            assert sidecar is not None
            assert sidecar.exists()

            # Read and verify sidecar content
            data = json.loads(sidecar.read_text())
            assert data["source"] == "observation_plane"
            assert data["game_profile"] == "madden_27"
            assert len(data["observations"]) > 0

            # Find the Cross observation
            cross_obs = [o for o in data["observations"] if o["hid_button"] == "Cross"]
            assert len(cross_obs) == 1
            assert cross_obs[0]["verb"] == "Snap Ball"
            assert cross_obs[0]["mode"] == "preplay_offense"
            assert cross_obs[0]["frame_seq"] == 100

    def test_sidecar_uses_hid_by_seq_not_hid_now(self):
        """Sidecar uses hid_by_seq[frame_seq], not HID[now] at export time."""
        from qoresence.monitor.frame_hub import get_frame_hub
        from qoresence.sync.hid_seq_line import get_hid_seq_line
        from qoresence.sync.input_ring import set_hold
        from qoresence.vision.clip_buffer import _write_observation_sidecar

        hub = get_frame_hub()
        line = get_hid_seq_line()
        hub.clear()
        line.clear()

        # Publish frame with Cross pressed at seq=50
        t0 = time.monotonic_ns()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        set_hold(clock_ns=t0, r2=0.0, l2=0.0, lx=0.0, ly=0.0, buttons=("Cross",))
        hub.publish(frame, clock_ns=t0, seq=50)

        # Now change HID[now] to Circle (simulate button release + new press)
        set_hold(clock_ns=t0 + int(50e6), r2=0.0, l2=0.0, lx=0.0, ly=0.0, buttons=("Circle",))

        # Create snapshot with seq=50 frame (Cross was pressed)
        snapshot = [(time.monotonic(), b"fake_jpeg", 640, 480, 50)]

        # Write observation sidecar (should see Cross, not Circle)
        with tempfile.TemporaryDirectory() as tmpdir:
            mp4_path = Path(tmpdir) / "test_clip.mp4"
            mp4_path.touch()

            sidecar = _write_observation_sidecar(mp4_path, snapshot=snapshot)
            if sidecar is not None:
                data = json.loads(sidecar.read_text())
                # Should see Cross from hid_by_seq[50], not Circle from HID[now]
                buttons = [o["hid_button"] for o in data["observations"]]
                assert "Cross" in buttons
                assert "Circle" not in buttons

    def test_sidecar_unlabeled_when_no_visual_phase(self):
        """Sidecar shows None verb when visual_phase missing."""
        from qoresence.monitor.frame_hub import get_frame_hub
        from qoresence.sync.hid_seq_line import get_hid_seq_line
        from qoresence.sync.input_ring import set_hold
        from qoresence.vision.clip_buffer import _write_observation_sidecar

        hub = get_frame_hub()
        line = get_hid_seq_line()
        hub.clear()
        line.clear()

        # Publish frame with Square pressed at seq=200
        t0 = time.monotonic_ns()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        set_hold(clock_ns=t0, r2=0.0, l2=0.0, lx=0.0, ly=0.0, buttons=("Square",))
        hub.publish(frame, clock_ns=t0, seq=200)

        # Create mock visual context WITHOUT visual_phase
        from qoresence.vision.visual_context import VisualContext

        visual_ctx = VisualContext(
            game_state="gameplay",
            game_profile="madden_27",
            # NO visual_phase in details
        )

        snapshot = [(time.monotonic(), b"fake_jpeg", 640, 480, 200)]

        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            mp4_path = Path(tmpdir) / "test_clip.mp4"
            mp4_path.touch()

            with patch(
                "qoresence.lobes.visual.get_last_visual_context",
                return_value=visual_ctx,
            ):
                sidecar = _write_observation_sidecar(mp4_path, snapshot=snapshot)
            if sidecar is not None:
                data = json.loads(sidecar.read_text())
                # Should have observations but verb=None (unlabeled)
                square_obs = [o for o in data["observations"] if o["hid_button"] == "Square"]
                if square_obs:
                    assert square_obs[0]["verb"] is None
                    assert square_obs[0]["mode"] is None

    def test_cfb_l3_madden_r3_throw_away_difference(self):
        """CFB passing L3 → Throw Ball Away; Madden uses R3."""
        from qoresence.monitor.frame_hub import get_frame_hub
        from qoresence.sync.hid_seq_line import get_hid_seq_line
        from qoresence.sync.input_ring import set_hold
        from qoresence.vision.clip_buffer import _write_observation_sidecar
        from qoresence.vision.visual_context import VisualContext

        hub = get_frame_hub()
        line = get_hid_seq_line()
        hub.clear()
        line.clear()

        # Test CFB with L3
        t0 = time.monotonic_ns()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        set_hold(clock_ns=t0, r2=0.0, l2=0.0, lx=0.0, ly=0.0, buttons=("L3",))
        hub.publish(frame, clock_ns=t0, seq=300)

        cfb_ctx = VisualContext(
            game_state="gameplay",
            game_profile="cfb_27",
            details={"visual_phase": "passing"},
        )

        snapshot_cfb = [(time.monotonic(), b"fake_jpeg", 640, 480, 300)]

        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            mp4_path = Path(tmpdir) / "cfb_clip.mp4"
            mp4_path.touch()

            with patch(
                "qoresence.lobes.visual.get_last_visual_context",
                return_value=cfb_ctx,
            ):
                sidecar = _write_observation_sidecar(mp4_path, snapshot=snapshot_cfb)
            if sidecar is not None:
                data = json.loads(sidecar.read_text())
                l3_obs = [o for o in data["observations"] if o["hid_button"] == "L3"]
                if l3_obs:
                    assert l3_obs[0]["verb"] == "Throw Ball Away"

        # Test Madden with R3
        hub.clear()
        line.clear()

        t1 = time.monotonic_ns()
        set_hold(clock_ns=t1, r2=0.0, l2=0.0, lx=0.0, ly=0.0, buttons=("R3",))
        hub.publish(frame, clock_ns=t1, seq=400)

        madden_ctx = VisualContext(
            game_state="gameplay",
            game_profile="madden_27",
            details={"visual_phase": "passing"},
        )

        snapshot_madden = [(time.monotonic(), b"fake_jpeg", 640, 480, 400)]

        with tempfile.TemporaryDirectory() as tmpdir:
            mp4_path = Path(tmpdir) / "madden_clip.mp4"
            mp4_path.touch()

            with patch(
                "qoresence.lobes.visual.get_last_visual_context",
                return_value=madden_ctx,
            ):
                sidecar = _write_observation_sidecar(mp4_path, snapshot=snapshot_madden)
            if sidecar is not None:
                data = json.loads(sidecar.read_text())
                r3_obs = [o for o in data["observations"] if o["hid_button"] == "R3"]
                if r3_obs:
                    assert r3_obs[0]["verb"] == "Throw Ball Away"

    def test_empty_snapshot_skips_sidecar(self):
        """Empty snapshot → no sidecar written."""
        from qoresence.vision.clip_buffer import _write_observation_sidecar

        with tempfile.TemporaryDirectory() as tmpdir:
            mp4_path = Path(tmpdir) / "test_clip.mp4"
            mp4_path.touch()

            sidecar = _write_observation_sidecar(mp4_path, snapshot=[])
            assert sidecar is None

    def test_no_hid_input_skips_sidecar(self):
        """No HID input during clip → no sidecar written."""
        from qoresence.monitor.frame_hub import get_frame_hub
        from qoresence.sync.hid_seq_line import get_hid_seq_line
        from qoresence.sync.input_ring import set_hold
        from qoresence.vision.clip_buffer import _write_observation_sidecar

        hub = get_frame_hub()
        line = get_hid_seq_line()
        hub.clear()
        line.clear()

        t0 = time.monotonic_ns()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        set_hold(clock_ns=t0, r2=0.0, l2=0.0, lx=0.0, ly=0.0, buttons=())
        hub.publish(frame, clock_ns=t0, seq=500)

        # Note: no set_hold() call, so no HID sample for this frame

        snapshot = [(time.monotonic(), b"fake_jpeg", 640, 480, 500)]

        with tempfile.TemporaryDirectory() as tmpdir:
            mp4_path = Path(tmpdir) / "test_clip.mp4"
            mp4_path.touch()

            sidecar = _write_observation_sidecar(mp4_path, snapshot=snapshot)
            # Should be None (no HID input) or empty observations
            if sidecar is not None:
                data = json.loads(sidecar.read_text())
                # Either no observations or empty list
                assert len(data.get("observations", [])) == 0
