"""Unit tests for FrameHub (no GUI)."""

from __future__ import annotations

import numpy as np

from qoresence.monitor.frame_hub import FrameHub, get_frame_hub, get_latest, publish


def test_empty_hub_returns_none():
    hub = FrameHub()
    assert hub.get_latest() is None
    frame, seq, age = hub.get_latest_meta()
    assert frame is None
    assert seq == 0
    st = hub.stats()
    assert st["has_frame"] is False


def test_publish_then_get_latest():
    hub = FrameHub()
    f = np.zeros((48, 64, 3), dtype=np.uint8)
    f[:, :] = (10, 20, 30)
    hub.publish(f)
    out = hub.get_latest()
    assert out is not None
    assert out.shape == (48, 64, 3)
    assert int(out[0, 0, 1]) == 20
    # Copy isolation
    f[:, :] = 0
    out2 = hub.get_latest()
    assert out2 is not None
    assert int(out2[0, 0, 1]) == 20
    frame, seq, age = hub.get_latest_meta()
    assert seq == 1
    assert age >= 0.0
    st = hub.stats()
    assert st["has_frame"] is True
    assert st["seq"] == 1
    assert st["width"] == 64


def test_module_helpers():
    # Use process hub; publish and read
    f = np.full((32, 40, 3), 7, dtype=np.uint8)
    publish(f)
    got = get_latest()
    assert got is not None
    assert got.shape[0] == 32
    assert get_frame_hub().stats()["has_frame"] is True


def test_publish_clock_ns_and_stamp():
    hub = FrameHub()
    f = np.zeros((8, 8, 3), dtype=np.uint8)
    t = 9_000_000_123
    hub.publish(f, clock_ns=t)
    st = hub.get_latest_stamp()
    assert st["has_frame"] is True
    assert st["seq"] == 1
    assert st["clock_ns"] == t
    assert hub.stats()["clock_ns"] == t
