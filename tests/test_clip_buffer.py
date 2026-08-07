"""Unit tests for HDMI clip buffer (latest_jpeg + stats)."""

from __future__ import annotations

import numpy as np

from qoresence.vision.clip_buffer import HdmiClipBuffer, get_latest_jpeg, get_clip_buffer


def test_latest_jpeg_empty_is_none():
    buf = HdmiClipBuffer(seconds=2, target_fps=10, max_width=160)
    assert buf.latest_jpeg() is None
    st = buf.stats()
    assert st["has_frame"] is False
    assert st["age_s"] is None
    assert st["frames"] == 0


def test_latest_jpeg_after_push():
    buf = HdmiClipBuffer(seconds=2, target_fps=100, max_width=160)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[:, :] = (20, 180, 40)
    buf.push(frame)
    jpg = buf.latest_jpeg()
    assert jpg is not None
    assert isinstance(jpg, (bytes, bytearray))
    assert len(jpg) > 50
    # JPEG SOI
    assert jpg[:2] == b"\xff\xd8"
    st = buf.stats()
    assert st["has_frame"] is True
    assert st["frames"] >= 1
    assert st["age_s"] is not None
    assert st["age_s"] >= 0.0


def test_get_latest_jpeg_module_helper():
    # Shared singleton may already have frames from other tests; ensure push works.
    b = get_clip_buffer(seconds=2, target_fps=50, max_width=160)
    before = b.latest_jpeg()
    f = np.full((100, 160, 3), 90, dtype=np.uint8)
    b.push(f)
    after = get_latest_jpeg()
    assert after is not None
    assert len(after) > 20
    # If buffer already had data, after is still latest bytes
    assert after == b.latest_jpeg()
