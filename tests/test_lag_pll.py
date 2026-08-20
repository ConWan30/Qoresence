"""Lag PLL + sub-frame luma bind (no hardware)."""

from __future__ import annotations

import numpy as np

from qoresence.monitor.frame_hub import FrameHub
from qoresence.sync.lag_estimator import LagEstimator
from qoresence.sync.optical import bind_offset_ms


def test_pll_ignores_stale_video():
    est = LagEstimator()
    for i in range(12):
        est.observe_phase(40.0 + i * 0.1, video_stale=False)
    snap = est.snapshot()
    assert snap["lag_center_ms"] is not None
    assert 38.0 <= snap["lag_center_ms"] <= 45.0
    frozen = snap["lag_center_ms"]
    for _ in range(20):
        est.observe_phase(200.0, video_stale=True)
    assert est.snapshot()["lag_center_ms"] == frozen


def test_pll_lock_after_stable_samples():
    est = LagEstimator()
    for _ in range(10):
        est.observe_phase(48.0)
    snap = est.snapshot()
    assert snap["pll_n"] >= 8
    assert snap["pll_lock"] is True
    assert snap["lag_jitter_ms"] is not None
    assert snap["lag_jitter_ms"] < 5.0


def test_pll_does_not_thin_default_band():
    est = LagEstimator()
    for _ in range(12):
        est.observe_phase(50.0)
    lo, hi = est.band(0.0, 120.0)
    assert lo <= 0.0 + 1e-6 or hi - lo >= 120.0
    assert hi - lo >= 80.0


def test_bind_offset_picks_luma_onset():
    t0 = 1_000_000_000
    ring = [
        {"clock_ns": t0, "energy": 0.1, "seq": 1},
        {"clock_ns": t0 + int(16e6), "energy": 0.2, "seq": 2},
        {"clock_ns": t0 + int(33e6), "energy": 6.0, "seq": 3},
        {"clock_ns": t0 + int(50e6), "energy": 1.0, "seq": 4},
    ]
    hid = t0 + int(30e6)
    off, conf = bind_offset_ms(ring, hid)
    assert off is not None
    assert conf > 0.0
    assert -16.0 <= off <= 16.0


def test_framehub_luma_ring_tracks_motion():
    hub = FrameHub()
    a = np.zeros((90, 160, 3), dtype=np.uint8)
    b = np.full((90, 160, 3), 80, dtype=np.uint8)
    hub.publish(a, clock_ns=10)
    hub.publish(b, clock_ns=20)
    ring = hub.luma_ring()
    assert len(ring) == 2
    assert ring[0]["energy"] == 0.0
    assert ring[1]["energy"] > 1.0
    assert ring[1]["seq"] == 2
