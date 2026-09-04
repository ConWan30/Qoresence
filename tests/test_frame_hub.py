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
    assert st.get("crop_hash", "") == ""


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


def test_streamer_publishes_hub_before_jpeg_encode():
    """WebRTC/Monitor must not wait on clip-buffer JPEG encode."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "qoresence" / "lobes" / "streamer.py").read_text(
        encoding="utf-8"
    )
    hub = src.find("_hub_publish(frame")
    clip = src.find("_clip_enqueue(frame)")
    assert hub > 0 and clip > hub


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


def test_stats_exposes_crop_hash_after_push():
    """Overlay liveCrop reads snap.video.crop_hash from FrameHub stats."""
    from qoresence.vision.scorebug_crops import CFB_PRIMARY_SCOREBUG, scorebug_crop_hash

    hub = FrameHub()
    h, w = 100, 200
    f = np.zeros((h, w, 3), dtype=np.uint8)
    hub.publish(f)
    st = hub.stats()
    assert st["has_frame"] is True
    ch = st["crop_hash"]
    assert isinstance(ch, str) and len(ch) == 16
    assert ch == scorebug_crop_hash(f)

    # Field motion outside the scorebug band must not move crop_hash.
    f_field = f.copy()
    f_field[: int(h * 0.50), :, :] = 180
    hub.publish(f_field)
    assert hub.stats()["crop_hash"] == ch

    # Scorebug-band paint is the liveCrop identity.
    x1, x2, y1, y2 = CFB_PRIMARY_SCOREBUG
    f_bug = f.copy()
    f_bug[int(h * y1) : int(h * y2), int(w * x1) : int(w * x2), :] = 255
    hub.publish(f_bug)
    bug = hub.stats()["crop_hash"]
    assert bug != ch
    assert len(bug) == 16
    assert bug == scorebug_crop_hash(f_bug)


def test_deck_snapshot_video_copies_hub_crop_hash():
    """snap.video.crop_hash is the FrameHub stamp overlay / pickBoard read."""
    from qoresence.deck.server import DeckState
    from qoresence.monitor.frame_hub import get_frame_hub

    hub = get_frame_hub()
    hub.clear()
    f = np.zeros((100, 200, 3), dtype=np.uint8)
    f[78:93, 24:176, :] = 90
    hub.publish(f)
    try:
        want = hub.stats()["crop_hash"]
        assert want
        video = DeckState()._snapshot_fresh()["video"]
        assert video.get("crop_hash") == want
    finally:
        hub.clear()


def test_sync_frame_hub_shim_meta():
    """Two-speed scaffold: qoresence.sync.frame_hub.get_latest_meta()."""
    from qoresence.sync.frame_hub import get_frame_hub, get_latest_meta
    from qoresence.sync.frame_hub import publish as sync_publish

    hub = get_frame_hub()
    hub.clear()
    f = np.zeros((4, 4, 3), dtype=np.uint8)
    sync_publish(f, clock_ns=111)
    meta = get_latest_meta()
    assert meta["has_frame"] is True
    assert meta["seq"] >= 1
    assert meta["clock_ns"] == 111
