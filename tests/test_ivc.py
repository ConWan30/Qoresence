"""IVC unit tests with fake ring + fake frame meta (no hardware)."""

from __future__ import annotations

import time

import numpy as np

from qoresence.monitor.frame_hub import FrameHub
from qoresence.sync.input_ring import InputEvent, InputRing
from qoresence.sync.ivc import InputVideoCoupler


class _FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def emit_raw(self, **kwargs):
        self.events.append(kwargs)
        return True


def test_ivc_no_frame_returns_none(monkeypatch):
    hub = FrameHub()
    ring = InputRing()
    monkeypatch.setattr("qoresence.monitor.frame_hub.get_frame_hub", lambda: hub)
    monkeypatch.setattr("qoresence.sync.input_ring.get_input_ring", lambda: ring)
    ivc = InputVideoCoupler(bus=None)
    assert ivc.tick_once() is None


def test_ivc_emits_coupling_with_frame_seq(monkeypatch):
    hub = FrameHub()
    ring = InputRing()
    bus = _FakeBus()

    t_video = time.monotonic_ns()
    # Press ~50 ms before frame (inside default 20–120 ms lag band)
    press_ns = t_video - int(50 * 1e6)
    ring.push(InputEvent(clock_ns=press_ns, kind="press", name="cross", value=1.0))
    ring.push(InputEvent(clock_ns=press_ns + 1000, kind="trigger", name="R2", value=0.9))

    f = np.zeros((8, 8, 3), dtype=np.uint8)
    hub.publish(f, clock_ns=t_video)

    monkeypatch.setattr("qoresence.monitor.frame_hub.get_frame_hub", lambda: hub)
    monkeypatch.setattr("qoresence.sync.input_ring.get_input_ring", lambda: ring)

    ivc = InputVideoCoupler(bus=bus, lag_lo_ms=20.0, lag_hi_ms=120.0)
    payload = ivc.tick_once()
    assert payload is not None
    assert payload["frame_seq"] == 1
    assert payload["video_clock_ns"] == t_video
    assert payload["input_events"] >= 1
    assert payload["input_energy"] > 0
    assert 0.0 < payload["coupling"] <= 1.0
    assert "cross" in payload["buttons"] or payload["input_events"] >= 1

    last = ivc.get_last_coupling()
    assert last["frame_seq"] == 1

    assert len(bus.events) == 1
    assert bus.events[0]["event_type"] == "coupling_score"
    assert bus.events[0]["payload"]["frame_seq"] == 1


def test_ivc_empty_inputs_zero_coupling(monkeypatch):
    from qoresence.sync.event_bind import get_event_binder

    get_event_binder().clear()
    hub = FrameHub()
    ring = InputRing()
    t_video = time.monotonic_ns()
    hub.publish(np.zeros((4, 4, 3), dtype=np.uint8), clock_ns=t_video)
    monkeypatch.setattr("qoresence.monitor.frame_hub.get_frame_hub", lambda: hub)
    monkeypatch.setattr("qoresence.sync.input_ring.get_input_ring", lambda: ring)
    ivc = InputVideoCoupler(bus=None)
    payload = ivc.tick_once()
    assert payload is not None
    assert payload["coupling"] == 0.0
    assert payload["input_events"] == 0
    assert payload["imu_bodied"] is False
    assert payload["binds"] == 0


def test_ivc_imu_bodied_names_precursor(monkeypatch):
    hub = FrameHub()
    ring = InputRing()
    t_video = time.monotonic_ns()
    press_ns = t_video - int(50 * 1e6)
    ring.push(
        InputEvent(
            clock_ns=press_ns,
            kind="press",
            name="R2",
            value=1.0,
            imu_precursor_ms=18.0,
        )
    )
    hub.publish(np.zeros((8, 8, 3), dtype=np.uint8), clock_ns=t_video)
    monkeypatch.setattr("qoresence.monitor.frame_hub.get_frame_hub", lambda: hub)
    monkeypatch.setattr("qoresence.sync.input_ring.get_input_ring", lambda: ring)
    ivc = InputVideoCoupler(bus=None, lag_lo_ms=20.0, lag_hi_ms=120.0)
    payload = ivc.tick_once()
    assert payload is not None
    assert payload["imu_bodied"] is True
    assert payload["imu_precursor_ms"] == 18.0
    assert payload["imu_precursor_name"] == "R2"
    assert payload["coupling"] > 0.0
