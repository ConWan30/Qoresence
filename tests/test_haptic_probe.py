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
    reset_haptic_probe()
    yield
    reset_haptic_probe()


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


# ── HID output rumble (emulated path) ────────────────────────────────────────


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


def test_synthetic_pulse_records_onset_and_ivc_window(tmp_path, monkeypatch):
    jsonl = tmp_path / "haptic.jsonl"
    probe = HapticProbe(
        enabled=True,
        session_id="haptic_sess",
        jsonl_path=jsonl,
        ivc_lookup=lambda: {
            "video_clock_ns": 5_010_000_000,
            "frame_seq": 77,
            "coupling": 0.62,
            "lag_band_ms": [0.0, 120.0],
            "lead_ms": 24.0,
        },
    )
    t0 = 5_000_000_000
    for i in range(90):
        ax, ay, az = _oscillating_accel(i)
        probe.observe_imu(
            clock_ns=t0 + i * 1_000_000,
            accel=(ax, ay, az),
            gyro=(4, 4, 4),
            analog_slew=0.0,
            transport="usb",
            hid_present=True,
        )
    for i in range(90, 150):
        probe.observe_imu(
            clock_ns=t0 + i * 1_000_000,
            accel=(0, 0, 1000),
            gyro=(4, 4, 4),
            analog_slew=0.0,
            transport="usb",
            hid_present=True,
        )
    probe.flush(timeout_s=2.0)
    rows = [r for r in probe.recent() if r.get("kind") == "haptic_transient"]
    assert rows, probe.recent()
    rec = rows[-1]
    assert rec["plane"] == "qoresence-observation"
    assert rec["session_id"] == "haptic_sess"
    assert rec["source_lobe"] == "controller"
    assert rec["t_end_ns"] > rec["t_start_ns"]
    assert rec["licenses"]["haptics_observed"] is True
    assert rec["licenses"]["haptics_coupled"] is True
    assert rec["licenses"]["haptics_confirmed"] is False
    assert rec["licenses"]["haptics_signature_known"] is False
    assert rec["qualification"] in {"candidate", "observed"}
    assert rec["coupled"] is True
    prov = rec["provenance"]
    assert prov["connection_mode"] == "usb"
    assert prov.get("video_clock_ns") == 5_010_000_000
    assert prov.get("in_ivc_window") is True
    assert "controller_bodied" not in rec
    probe.stop()
    assert jsonl.exists()
    dumped = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(r.get("kind") == "haptic_transient" for r in dumped)


def test_unbodied_pulse_does_not_set_controller_bodied(tmp_path):
    probe = HapticProbe(enabled=True, session_id="unbodied", jsonl_path=tmp_path / "h.jsonl")
    t0 = 9_000_000_000
    probe.observe_output_report(
        pack_output_report(rumble_right=180, rumble_left=90, transport="usb"),
        clock_ns=t0,
        hid_present=False,
    )
    probe.observe_output_report(
        pack_output_report(rumble_right=0, rumble_left=0, transport="usb"),
        clock_ns=t0 + 80_000_000,
        hid_present=False,
    )
    probe.flush(timeout_s=2.0)
    rows = [r for r in probe.recent() if r.get("kind") == "haptic_transient"]
    assert rows
    rec = rows[-1]
    assert rec["licenses"]["haptics_observed"] is True
    assert rec["coupled"] is False
    assert rec["licenses"]["haptics_coupled"] is False
    assert "controller_bodied" not in rec
    tick = CoupledTickRecord(
        session_id="unbodied",
        clock_ns=t0,
        frame_seq=1,
        input_ticks=[],
        situation=None,
        board_locked=False,
        controller_bodied=False,
        body_reason="pad_not_on_this_host",
    ).to_dict()
    assert tick["controller_bodied"] is False
    probe.stop()


def test_unavailable_channel_emits_no_claim_without_crash(tmp_path):
    probe = HapticProbe(enabled=True, session_id="empty", jsonl_path=tmp_path / "h.jsonl")
    rec = probe.record_unavailable(clock_ns=1, reason="no_hid")
    assert rec["kind"] == "haptic_unavailable"
    assert rec["plane"] == "qoresence-observation"
    assert rec["licenses"]["haptics_observed"] is False
    assert rec.get("intensity") is None
    assert rec.get("t_start_ns") is None
    probe.flush(timeout_s=1.0)
    probe.stop()


def test_hot_path_enqueue_does_not_block_when_queue_full(tmp_path):
    probe = HapticProbe(
        enabled=True,
        session_id="flood",
        jsonl_path=None,
        queue_size=8,
        stall_worker=True,
    )
    t0 = time.monotonic_ns()
    start = time.perf_counter()
    for i in range(4000):
        probe.observe_imu(
            clock_ns=t0 + i * 1_000_000,
            accel=_oscillating_accel(i),
            gyro=(0, 0, 0),
        )
    elapsed = time.perf_counter() - start
    probe.stop()
    assert elapsed < 0.75, f"hot path blocked ({elapsed:.3f}s)"


def test_probe_does_not_emit_bus_events(tmp_path):
    from qoresence.core import RetinaEventBus

    bus = RetinaEventBus(session_id="no_bus", jsonl_path=tmp_path / "e.jsonl", enable_ws=False)
    seen: list[str] = []
    bus.subscribe(lambda ev: seen.append(getattr(getattr(ev, "type", ""), "value", str(ev))))
    probe = HapticProbe(enabled=True, session_id="no_bus", jsonl_path=tmp_path / "h.jsonl")
    t0 = 8_000_000_000
    for i in range(100):
        probe.observe_imu(
            clock_ns=t0 + i * 1_000_000,
            accel=_oscillating_accel(i),
            gyro=(4, 4, 4),
            hid_present=True,
            transport="usb",
        )
    probe.flush(timeout_s=2.0)
    probe.stop()
    bus.close()
    assert seen == []


def test_output_rumble_pulse_is_attributed(tmp_path):
    probe = HapticProbe(enabled=True, session_id="rumble", jsonl_path=tmp_path / "h.jsonl")
    t0 = 4_000_000_000
    probe.observe_output_report(
        pack_output_report(rumble_right=10, rumble_left=250, transport="bt"),
        clock_ns=t0,
        hid_present=True,
        transport="bt",
    )
    probe.observe_output_report(
        pack_output_report(rumble_right=0, rumble_left=0, transport="bt"),
        clock_ns=t0 + 40_000_000,
        hid_present=True,
        transport="bt",
    )
    probe.flush(timeout_s=2.0)
    rows = [r for r in probe.recent() if r.get("kind") == "haptic_transient"]
    assert rows
    rec = rows[-1]
    assert rec["channel"] == "hid_output"
    assert rec["provenance"]["connection_mode"] == "bt"
    assert "left" in rec.get("actuators", [])
    assert rec["licenses"]["haptics_confirmed"] is False
    probe.stop()


def test_start_from_env_and_stop_is_private(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_HAPTIC_PROBE", "1")
    p = start_haptic_probe(session_id="env1", out_dir=tmp_path)
    assert p is not None and p.enabled
    stop_haptic_probe()
    observe_imu(clock_ns=1, accel=(0, 0, 1000), gyro=(0, 0, 0))
    assert recent_records() == []


def test_ingest_report_feeds_probe_without_opening_capture(tmp_path):
    from qoresence.core import ControllerConfig, RetinaEventBus, SessionAuthority
    from qoresence.lobes.controller import ControllerRuntime
    from qoresence.sync.hid_report import pack_usb_report

    bus = RetinaEventBus(session_id="wire", jsonl_path=tmp_path / "e.jsonl", enable_ws=False)
    identity = SessionAuthority.mint(session_id="wire")
    runtime = ControllerRuntime(
        config=ControllerConfig(enabled=True),
        bus=bus,
        session_head_ns=identity.session_head_ns,
    )
    probe = HapticProbe(enabled=True, session_id="wire", jsonl_path=tmp_path / "h.jsonl")
    start_haptic_probe(probe=probe)
    t0 = time.monotonic_ns()
    for i in range(100):
        runtime.ingest_report(
            pack_usb_report(gyro=(4, 4, 4), accel=_oscillating_accel(i)),
            host_ts_ns=t0 + i * 1_000_000,
        )
    for i in range(100, 150):
        runtime.ingest_report(
            pack_usb_report(gyro=(4, 4, 4), accel=(0, 0, 1000)),
            host_ts_ns=t0 + i * 1_000_000,
        )
    probe.flush(timeout_s=2.0)
    rows = [r for r in probe.recent() if r.get("kind") == "haptic_transient"]
    assert rows, probe.recent()
    probe.stop()
    bus.close()


def test_bodied_r2_fixture_does_not_invent_haptic_from_precursor(tmp_path):
    from qoresence.core import ControllerConfig, RetinaEventBus, SessionAuthority
    from qoresence.lobes.controller import ControllerRuntime
    from qoresence.sync.dualsense_fixture import feed_bodied_r2

    bus = RetinaEventBus(session_id="fix", jsonl_path=tmp_path / "e.jsonl", enable_ws=False)
    identity = SessionAuthority.mint(session_id="fix")
    runtime = ControllerRuntime(
        config=ControllerConfig(enabled=True),
        bus=bus,
        session_head_ns=identity.session_head_ns,
    )
    probe = HapticProbe(enabled=True, session_id="fix", jsonl_path=tmp_path / "h.jsonl")
    start_haptic_probe(probe=probe)
    feed_bodied_r2(runtime)
    probe.flush(timeout_s=2.0)
    trans = [r for r in probe.recent() if r.get("kind") == "haptic_transient"]
    probe.stop()
    bus.close()
    assert trans == []


# ── Phase 2 private metrics ──────────────────────────────────────────────────


def test_corroboration_metrics_from_logs_are_reproducible():
    haptic = [
        {
            "kind": "haptic_transient",
            "t_start_ns": 100_000_000,
            "t_end_ns": 180_000_000,
            "coupled": True,
            "licenses": {"haptics_observed": True, "haptics_coupled": True},
            "provenance": {"video_clock_ns": 110_000_000, "in_ivc_window": True, "coupling": 0.7},
        },
        {
            "kind": "haptic_transient",
            "t_start_ns": 900_000_000,
            "t_end_ns": 940_000_000,
            "coupled": True,
            "licenses": {"haptics_observed": True, "haptics_coupled": True},
            "provenance": {"video_clock_ns": None, "in_ivc_window": False, "coupling": 0.0},
        },
        empty_record(session_id="m", clock_ns=1, reason="channel_unavailable"),
    ]
    ticks = [
        {
            "clock_ns": 112_000_000,
            "board_locked": True,
            "controller_bodied": False,
            "coupling": {"coupling": 0.7, "video_clock_ns": 110_000_000},
            "situation_snapshot": {"home_score": 14, "away_score": 7},
        },
        {
            "clock_ns": 500_000_000,
            "board_locked": False,
            "controller_bodied": False,
            "coupling": {"coupling": 0.05},
        },
    ]
    a = corroboration_report(haptic, civif_ticks=ticks, window_ms=120.0)
    b = corroboration_report(haptic, civif_ticks=ticks, window_ms=120.0)
    assert a == b
    assert a["n_transients"] == 2
    assert a["n_unavailable"] == 1
    assert a["n_in_ivc_window"] == 1
    assert a["n_near_board_lock"] >= 1
    assert a["claim_ceiling"] == "co_occurrence_only"
    assert a["haptics_confirmed_license"] is False
    assert "public_surfaces" not in a or a.get("public_surfaces") is False
    assert set(a["six_category"]) == {
        "presence",
        "attribution",
        "connection_mode",
        "temporal_join",
        "board_corroboration",
        "false_positive",
    }
    assert a["precision_proxy"] is not None
    assert a["recall_proxy"] is not None


def test_session_report_loads_jsonl_and_clip_sidecar(tmp_path):
    haptic_path = tmp_path / "h.jsonl"
    civif_path = tmp_path / "civif.jsonl"
    clips = tmp_path / "clips"
    clips.mkdir()
    haptic_path.write_text(
        json.dumps(
            {
                "kind": "haptic_transient",
                "t_start_ns": 200_000_000,
                "coupled": True,
                "licenses": {"haptics_observed": True, "haptics_coupled": True},
                "provenance": {
                    "video_clock_ns": 190_000_000,
                    "in_ivc_window": True,
                    "coupling": 0.8,
                    "connection_mode": "usb",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    civif_path.write_text(
        json.dumps(
            {
                "clock_ns": 205_000_000,
                "board_locked": True,
                "situation_snapshot": {"home_score": 7, "away_score": 0},
                "coupling": {"phrase": "SPRINT", "coupling": 0.8},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (clips / "hdmi_clip_x.coupling.json").write_text(
        json.dumps(
            {
                "video": {"t_start_ns": 198_000_000},
                "situation": {"clutch_kind": "score_changed"},
            }
        ),
        encoding="utf-8",
    )
    from qoresence.sync.haptic_metrics import session_report

    rep = session_report(haptic_path, civif_jsonl=civif_path, clips_dir=clips)
    assert rep["n_transients"] == 1
    assert rep["n_event_markers"] >= 1
    assert rep["connection_modes"] == ["usb"]
    assert rep["six_category"]["presence"] > 0
    assert rep["haptics_confirmed_license"] is False
    assert rep["public_surfaces"] is False


def test_menu_pause_pulse_counts_as_false_positive_proxy():
    haptic = [
        {
            "kind": "haptic_transient",
            "t_start_ns": 50_000_000,
            "coupled": True,
            "licenses": {"haptics_observed": True, "haptics_coupled": True},
            "provenance": {"in_ivc_window": False, "coupling": 0.0, "connection_mode": "bt"},
        }
    ]
    ticks = [
        {
            "clock_ns": 48_000_000,
            "board_locked": False,
            "coupling": {"phrase": "IDLE", "game_state": "pause"},
        }
    ]
    rep = corroboration_report(haptic, civif_ticks=ticks, window_ms=120.0)
    assert rep["menu_pause_false_positive_proxy"] >= 1
    assert rep["six_category"]["false_positive"] < 1.0
