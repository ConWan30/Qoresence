"""Private haptic observation channel — schema, fail-closed probe, corroboration.

Observation plane only. Haptic pulse != confirmed gameplay event.
"""

from __future__ import annotations

import json
import math
import time

import pytest

from qoresence.core.civif_tick import CoupledTickRecord
from qoresence.sync.haptic_echo import EchoDetector
from qoresence.sync.haptic_metrics import corroboration_report
from qoresence.sync.haptic_output import pack_output_report, parse_output_rumble
from qoresence.sync.haptic_probe import (
    HapticProbe,
    observe_imu,
    recent_records,
    reset_haptic_probe,
    start_haptic_probe,
    stop_haptic_probe,
)
from qoresence.sync.haptic_receipt import reset_receipt_clock
from qoresence.sync.haptic_schema import (
    HAPTIC_PLANE,
    HAPTIC_SCHEMA,
    empty_record,
    intensity_bucket,
    licenses_fail_closed,
    validate_record,
)


@pytest.fixture(autouse=True)
def _isolate_probe(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_HAPTIC_PROBE", raising=False)
    monkeypatch.delenv("QORESENCE_HAPTIC_RECEIPT", raising=False)
    reset_haptic_probe()
    reset_receipt_clock()
    yield
    reset_haptic_probe()
    reset_receipt_clock()


def _oscillating_accel(i: int, *, amp: int = 420, hz: float = 125.0, rest: int = 1000) -> tuple[int, int, int]:
    z = rest + int(amp * math.sin(2.0 * math.pi * hz * (i / 1000.0)))
    return (0, 0, z)


# ── Schema ───────────────────────────────────────────────────────────────────


def test_schema_hard_plane_and_staged_licenses():
    rec = empty_record(session_id="s1", clock_ns=10, reason="channel_unavailable")
    assert rec["plane"] == HAPTIC_PLANE == "qoresence-observation"
    assert rec["schema_version"] == HAPTIC_SCHEMA
    assert rec["source_lobe"] == "controller"
    assert rec["kind"] == "haptic_unavailable"
    assert rec["qualification"] in {"candidate", "observed"}
    lic = rec["licenses"]
    assert lic == {
        "haptics_observed": False,
        "haptics_coupled": False,
        "haptics_signature_known": False,
        "haptics_confirmed": False,
    }
    assert "controller_bodied" not in rec
    assert rec.get("intensity") is None
    assert rec.get("t_start_ns") is None
    errs = validate_record(rec)
    assert errs == []


def test_intensity_bucket_never_emits_raw_device_units():
    assert intensity_bucket(0.05) == "low"
    assert intensity_bucket(0.40) == "mid"
    assert intensity_bucket(0.85) == "high"
    assert intensity_bucket(None) is None
    closed = licenses_fail_closed(observed=True, coupled=True, signature_known=True, confirmed=True)
    assert closed["haptics_signature_known"] is False
    assert closed["haptics_confirmed"] is False
    assert closed["haptics_observed"] is True
    assert closed["haptics_coupled"] is True


# ── Echo detector (IMU as actuator microphone) ────────────────────────────────


def test_echo_detector_emits_onset_offset_for_sustained_oscillation():
    det = EchoDetector()
    t0 = 1_000_000_000
    pulse = None
    for i in range(90):
        ax, ay, az = _oscillating_accel(i)
        pulse = det.feed(
            clock_ns=t0 + i * 1_000_000,
            accel=(ax, ay, az),
            gyro=(4, 4, 4),
            analog_slew=0.0,
        ) or pulse
    # trailing quiet closes the pulse
    ended = None
    for i in range(90, 140):
        ended = det.feed(
            clock_ns=t0 + i * 1_000_000,
            accel=(0, 0, 1000),
            gyro=(4, 4, 4),
            analog_slew=0.0,
        )
        if ended is not None:
            break
    assert ended is not None
    assert ended.t_end_ns > ended.t_start_ns
    assert ended.duration_ms >= 20.0
    assert ended.intensity in {"low", "mid", "high"}
    assert ended.channel == "imu_echo"
    assert ended.signature in {"impact_candidate", "sustained", None}


def test_echo_detector_ignores_press_precursor_gyro_jolt():
    """L2B precursor is a brief gyro spike with flat accel — not haptic echo."""
    det = EchoDetector()
    t0 = 2_000_000_000
    for i in range(40):
        gyro = (80, 10, 10) if i == 25 else (5, 5, 5)
        got = det.feed(
            clock_ns=t0 + i * 1_000_000,
            accel=(0, 0, 1000),
            gyro=gyro,
            analog_slew=0.0,
        )
        assert got is None


def test_echo_detector_downweights_analog_slew():
    det = EchoDetector()
    t0 = 3_000_000_000
    for i in range(80):
        ax, ay, az = _oscillating_accel(i, amp=80)
        got = det.feed(
            clock_ns=t0 + i * 1_000_000,
            accel=(ax, ay, az),
            gyro=(4, 4, 4),
            analog_slew=1.2,
        )
        assert got is None


# ── HID output rumble (emulated path) ──────────────────────────────────────


def test_parse_usb_and_bt_output_rumble_roundtrip():
    usb = pack_output_report(rumble_right=40, rumble_left=200, transport="usb")
    bt = pack_output_report(rumble_right=40, rumble_left=200, transport="bt")
    pu, pb = parse_output_rumble(usb), parse_output_rumble(bt)
    assert pu is not None and pb is not None
    assert pu["transport"] == "usb"
    assert pb["transport"] == "bt"
    assert pu["rumble_right"] == pb["rumble_right"] == 40
    assert pu["rumble_left"] == pb["rumble_left"] == 200
    assert parse_output_rumble(b"") is None
    assert parse_output_rumble(bytes(64)) is None


# ── Probe runtime ────────────────────────────────────────────────────────────


def test_default_off_zero_observation_activity(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_HAPTIC_PROBE", raising=False)
    reset_haptic_probe()
    t0 = time.monotonic_ns()
    for i in range(50):
        ax, ay, az = _oscillating_accel(i)
        observe_imu(
            clock_ns=t0 + i * 1_000_000,
            accel=(ax, ay, az),
            gyro=(0, 0, 0),
        )
    assert recent_records() == []
    assert list(tmp_path.glob("**/*haptic*")) == []

