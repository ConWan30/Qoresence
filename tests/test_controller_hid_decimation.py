"""HID analog decimation: button/trigger edges exact, analog-only reports thinned.

Live 2026-10-13 (Madden 27, DualSense Edge on USB to the laptop and BT to the
PS5): capture fell from 30 to 4-8 fps while the pad streamed ~440 reports/s
through the full per-report Python path. Unchanged button/trigger reports are
now fully processed at ``QORESENCE_HID_ANALOG_HZ`` (default 125).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from qoresence.core import ControllerConfig, RetinaEventBus, SessionAuthority
from qoresence.lobes.controller import ControllerRuntime
from qoresence.sync.hid_report import CROSS, SQUARE, pack_usb_report


@pytest.fixture
def rt(tmp_path: Path):
    bus = RetinaEventBus(session_id="dec", jsonl_path=tmp_path / "e.jsonl", enable_ws=False)
    ident = SessionAuthority.mint(session_id="dec")
    r = ControllerRuntime(
        config=ControllerConfig(enabled=True),
        bus=bus,
        session_head_ns=ident.session_head_ns,
        presence_touch_file=tmp_path / "p.touch",
    )
    yield r
    bus.close()


def _stream(n=2000, hz=1000):
    """Sticks always moving + IMU noise; presses at fixed report indices."""
    presses = {100: CROSS, 101: 0, 500: SQUARE, 503: 0, 900: CROSS | SQUARE, 902: CROSS, 905: 0}
    buttons = 0
    out = []
    t0 = 1_000_000_000
    for i in range(n):
        buttons = presses.get(i, buttons)
        r2 = 200 if 1200 <= i < 1210 else 0
        out.append(
            (
                t0 + i * int(1e9 / hz),
                pack_usb_report(
                    buttons=buttons,
                    r2=r2,
                    lx=60 + (i % 50),
                    ly=200 - (i % 40),
                    gyro=(i % 7, -(i % 5), 3),
                    accel=(100, 8000 + (i % 3), -50),
                ),
            )
        )
    return out


def _run(rt, stream, decimate):
    edges = []
    triggers = []
    orig = rt._emit_button_events

    def spy(pressed, released, now_ns, hid_domain="play"):
        edges.append((pressed, released))
        return orig(pressed, released, now_ns, hid_domain=hid_domain)

    rt._emit_button_events = spy
    orig_emit = rt.bus.emit_raw

    def emit(*a, **k):
        if k.get("event_type") == "trigger_onset":
            triggers.append(k["payload"]["trigger"])
        return orig_emit(*a, **k)

    rt.bus.emit_raw = emit
    full = 0
    for ts, rep in stream:
        if decimate and rt._decimate(rep, ts):
            continue
        full += 1
        rt.ingest_report(rep, host_ts_ns=ts)
    return edges, triggers, full


def test_button_and_trigger_edges_exact(rt, tmp_path):
    stream = _stream()
    edges_d, trig_d, full_d = _run(rt, stream, decimate=True)
    bus = RetinaEventBus(session_id="ref", jsonl_path=tmp_path / "r.jsonl", enable_ws=False)
    ref = ControllerRuntime(
        config=ControllerConfig(enabled=True),
        bus=bus,
        session_head_ns=0,
        presence_touch_file=tmp_path / "q.touch",
    )
    edges_f, trig_f, full_f = _run(ref, stream, decimate=False)
    bus.close()
    assert edges_d == edges_f and len(edges_f) == 7
    assert trig_d == trig_f == ["R2"]
    assert full_f == len(stream)
    # 1 kHz in, ~125 Hz analog + edges out.
    assert full_d <= len(stream) * 0.2, full_d


def test_unchanged_reports_processed_at_analog_rate(rt):
    rep = pack_usb_report(lx=30)
    t = 10_000_000_000
    assert rt._decimate(rep, t) is False  # first sight of this key
    assert rt._decimate(pack_usb_report(lx=40), t + 1_000_000) is True  # motion, same deadzone side
    assert rt._decimate(pack_usb_report(lx=128), t + 2_000_000) is False  # back to center: edge
    assert rt._decimate(pack_usb_report(lx=40), t + 2_500_000) is False  # out again: edge
    assert rt._decimate(pack_usb_report(lx=30), t + 3_000_000) is True
    t2 = t + 2_500_000 + rt._analog_period_ns
    assert rt._decimate(rep, t2) is False  # analog due
    assert rt._decimate(pack_usb_report(lx=30, buttons=CROSS), t2 + 1) is False


def test_bt_offsets_use_shifted_key(rt):
    bt = bytearray(78)
    bt[0] = 0x31
    t = 5_000_000_000
    assert rt._decimate(bytes(bt), t) is False
    bt2 = bytearray(bt)
    bt2[9] = 0x20  # BT buttons_0 (USB 8 + 1)
    assert rt._decimate(bytes(bt2), t + 1000) is False
    bt3 = bytearray(bt2)
    bt3[8] = 0x55  # BT byte 8 = USB counter byte 7: not part of the key
    assert rt._decimate(bytes(bt3), t + 2000) is True


def test_benchmark_decimated_path_is_cheap(rt):
    """Per-report cost: decimated reports must cost a small fraction of full ones."""
    stream = _stream(n=3000)
    t0 = time.perf_counter()
    for ts, rep in stream:
        rt.ingest_report(rep, host_ts_ns=ts)
    full_s = time.perf_counter() - t0
    rt._last_edge_key = None
    t0 = time.perf_counter()
    for ts, rep in stream:
        if not rt._decimate(rep, ts):
            rt.ingest_report(rep, host_ts_ns=ts)
    dec_s = time.perf_counter() - t0
    print(f"full {full_s * 1e6 / len(stream):.1f} us/report, decimated {dec_s * 1e6 / len(stream):.1f} us/report")
    assert dec_s < full_s * 0.5
