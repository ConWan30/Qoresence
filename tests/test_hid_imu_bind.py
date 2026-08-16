"""HID parser, IMU precursor, temporal bind, adaptive lag — observation plane."""

from __future__ import annotations

import time

import numpy as np

from qoresence.sync.event_bind import HidOnset, VisualOnset, bind_onsets
from qoresence.sync.hid_report import (
    CROSS,
    TransportType,
    detect_transport,
    pack_usb_report,
    parse_report,
)
from qoresence.sync.imu_ring import IMU_SPIKE_THRESH, ImuRing
from qoresence.sync.lag_estimator import LagEstimator
from qoresence.sync.optical import frame_motion_energy, pearson


def test_parse_usb_cross_and_imu():
    raw = pack_usb_report(buttons=CROSS, r2=180, gyro=(120, -40, 80), accel=(1000, 0, 9000))
    assert detect_transport(raw) == TransportType.USB
    p = parse_report(raw)
    assert p["transport"] == "usb"
    assert p["buttons"] & CROSS
    assert p["r2"] == 180
    assert p["gyro_x"] == 120
    assert p["gyro_z"] == 80


def test_bt_shift_matches_usb_state():
    usb = pack_usb_report(buttons=CROSS, l2=40, lx=140, gyro=(50, 0, 0))
    bt = bytearray(78)
    bt[0] = 0x31
    bt[1] = 0x00
    for i in range(1, 64):
        bt[i + 1] = usb[i]
    pu, pb = parse_report(bytes(usb)), parse_report(bytes(bt))
    assert pu["buttons"] == pb["buttons"]
    assert pu["l2"] == pb["l2"]
    assert pu["lx"] == pb["lx"]
    assert pu["gyro_x"] == pb["gyro_x"]


def test_imu_precursor_detects_jolt_before_press():
    ring = ImuRing()
    t0 = time.monotonic_ns()
    for i in range(30):
        ring.push_raw(t0 + i * 1_000_000, gyro=(5, 5, 5), accel=(0, 0, 1000))
    # spike 25 ms before press
    press = t0 + 80_000_000
    ring.push_raw(press - int(25e6), gyro=(80, 10, 10), accel=(0, 0, 1000))
    ms = ring.precursor_ms(press, thresh=0.02)
    assert ms is not None
    assert 15.0 <= ms <= 40.0


def test_imu_precursor_none_without_jolt():
    ring = ImuRing()
    t0 = time.monotonic_ns()
    for i in range(40):
        ring.push_raw(t0 + i * 1_000_000, gyro=(4, 4, 4), accel=(0, 0, 1000))
    assert ring.precursor_ms(t0 + 50_000_000, thresh=IMU_SPIKE_THRESH) is None


def test_bind_pairs_score_to_prior_r2():
    t = 1_000_000_000
    binds = bind_onsets(
        [VisualOnset(clock_ns=t + 80_000_000, kind="score_changed", frame_seq=12)],
        [
            HidOnset(clock_ns=t + 20_000_000, name="R2", kind="trigger", imu_precursor_ms=18.0),
            HidOnset(clock_ns=t - 500_000_000, name="cross", kind="press"),
        ],
        window_ms=400,
    )
    assert len(binds) == 1
    assert binds[0].mode == "TEMPORAL"
    assert binds[0].hid_name == "R2"
    assert binds[0].visual_kind == "score_changed"
    assert 50 <= binds[0].lag_ms <= 70
    assert binds[0].imu_precursor_ms == 18.0


def test_lag_estimator_slides_band():
    est = LagEstimator()
    lo, hi = est.band(20.0, 120.0)
    assert (lo, hi) == (20.0, 120.0)
    for lag in (40, 42, 45, 48, 50, 52, 55, 58):
        est.observe(float(lag))
    lo, hi = est.band(20.0, 120.0)
    # Widen-only: configured [20, 120] is a floor, mid-band samples do not shrink it
    assert lo == 20.0
    assert hi == 120.0


def test_lag_estimator_late_binds_do_not_raise_lo():
    """Live bug: 200 ms first-down binds slid the window to 191–227 and killed coupling."""
    est = LagEstimator()
    for lag in (190, 200, 205, 210, 220):
        est.observe(float(lag))
    lo, hi = est.band(0.0, 120.0)
    assert lo == 0.0
    assert hi >= 200.0
    assert hi <= 280.0


def test_optical_motion_and_pearson():
    a = np.zeros((8, 8), dtype=np.uint8)
    b = np.full((8, 8), 40, dtype=np.uint8)
    assert frame_motion_energy(a, b) > 0
    xs = [float(i) for i in range(16)]
    ys = [float(i) * 2 for i in range(16)]
    assert pearson(xs, ys) > 0.9
