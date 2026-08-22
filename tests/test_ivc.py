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
    from qoresence.sync.lag_estimator import get_lag_estimator

    get_lag_estimator().reset()
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
    assert payload["lag_center_ms"] is not None
    assert payload["pll_n"] >= 1
    assert "bind_offset_ms" in payload


def test_ivc_hold_couples_without_edge_in_window(monkeypatch):
    """Sprint hold after the onset aged out of the lag band still couples."""
    hub = FrameHub()
    ring = InputRing()
    t_video = time.monotonic_ns()
    # No edges in the 20–120 ms band; analog hold is live at sample time
    ring.set_hold(clock_ns=t_video, r2=0.92, l2=0.0, left=0.0, right=0.0)
    hub.publish(np.zeros((8, 8, 3), dtype=np.uint8), clock_ns=t_video)
    monkeypatch.setattr("qoresence.monitor.frame_hub.get_frame_hub", lambda: hub)
    monkeypatch.setattr("qoresence.sync.input_ring.get_input_ring", lambda: ring)
    ivc = InputVideoCoupler(bus=None, lag_lo_ms=20.0, lag_hi_ms=120.0)
    payload = ivc.tick_once()
    assert payload is not None
    assert payload["input_events"] == 0
    assert payload["hold_energy"] > 0.0
    assert payload["edge_energy"] == 0.0
    assert payload["coupling"] > 0.0
    assert payload["coupling_ema"] > 0.0


def test_ivc_stale_hold_zero(monkeypatch):
    hub = FrameHub()
    ring = InputRing()
    t_video = time.monotonic_ns()
    ring.set_hold(clock_ns=t_video - int(500 * 1e6), r2=1.0)
    hub.publish(np.zeros((4, 4, 3), dtype=np.uint8), clock_ns=t_video)
    monkeypatch.setattr("qoresence.monitor.frame_hub.get_frame_hub", lambda: hub)
    monkeypatch.setattr("qoresence.sync.input_ring.get_input_ring", lambda: ring)
    ivc = InputVideoCoupler(bus=None)
    payload = ivc.tick_once()
    assert payload is not None
    assert payload["hold_energy"] == 0.0
    assert payload["coupling"] == 0.0


def test_ivc_near_simultaneous_edge_joins(monkeypatch):
    """5 ms before the frame used to miss the 20 ms lag_lo floor."""
    hub = FrameHub()
    ring = InputRing()
    t_video = time.monotonic_ns()
    ring.push(InputEvent(clock_ns=t_video - int(5 * 1e6), kind="press", name="cross", value=1.0))
    hub.publish(np.zeros((8, 8, 3), dtype=np.uint8), clock_ns=t_video)
    monkeypatch.setattr("qoresence.monitor.frame_hub.get_frame_hub", lambda: hub)
    monkeypatch.setattr("qoresence.sync.input_ring.get_input_ring", lambda: ring)
    ivc = InputVideoCoupler(bus=None, lag_lo_ms=0.0, lag_hi_ms=120.0, lead_ms=24.0)
    payload = ivc.tick_once()
    assert payload is not None
    assert payload["input_events"] >= 1
    assert payload["edge_energy"] > 0.0
    assert payload["coupling"] > 0.0


def test_ivc_lead_includes_slightly_after_frame(monkeypatch):
    hub = FrameHub()
    ring = InputRing()
    t_video = time.monotonic_ns()
    ring.push(InputEvent(clock_ns=t_video + int(10 * 1e6), kind="trigger", name="R2", value=0.8))
    hub.publish(np.zeros((8, 8, 3), dtype=np.uint8), clock_ns=t_video)
    monkeypatch.setattr("qoresence.monitor.frame_hub.get_frame_hub", lambda: hub)
    monkeypatch.setattr("qoresence.sync.input_ring.get_input_ring", lambda: ring)
    ivc = InputVideoCoupler(bus=None, lag_lo_ms=0.0, lag_hi_ms=120.0, lead_ms=24.0)
    payload = ivc.tick_once()
    assert payload is not None
    assert payload["input_events"] >= 1
    assert payload["coupling"] > 0.0


def test_ivc_sprint_hold_phrase_off_no_ticket(monkeypatch):
    """Phrase lattice OFF: hold still couples, but no SPRINT mint."""
    from qoresence.sync.coupling_ticket import reset_coupling_book
    from qoresence.sync.lag_estimator import get_lag_estimator
    from qoresence.sync.play_phrase import note_game_state

    reset_coupling_book()
    note_game_state("gameplay")
    est = get_lag_estimator()
    est.reset()
    for i in range(10):
        est.observe_phase(40.0 + 0.1 * i)
    hub = FrameHub()
    ring = InputRing()
    t_video = time.monotonic_ns()
    ring.set_hold(clock_ns=t_video, r2=0.95, l2=0.0, left=0.0, right=0.0)
    hub.publish(np.zeros((8, 8, 3), dtype=np.uint8), clock_ns=t_video)
    monkeypatch.setattr("qoresence.monitor.frame_hub.get_frame_hub", lambda: hub)
    monkeypatch.setattr("qoresence.sync.input_ring.get_input_ring", lambda: ring)
    ivc = InputVideoCoupler(bus=None)
    payload = ivc.tick_once()
    assert payload is not None
    assert payload["phrase"] == "IDLE"
    assert payload["pll_lock"] is True
    assert not payload["coupling_ticket_id"]
    assert payload.get("coupling", 0) >= 0.0


def test_ivc_sprint_without_pll_does_not_mint(monkeypatch):
    from qoresence.sync.coupling_ticket import reset_coupling_book
    from qoresence.sync.lag_estimator import get_lag_estimator
    from qoresence.sync.play_phrase import note_game_state

    reset_coupling_book()
    get_lag_estimator().reset()
    note_game_state("gameplay")
    hub = FrameHub()
    ring = InputRing()
    t_video = time.monotonic_ns()
    ring.set_hold(clock_ns=t_video, r2=0.95, l2=0.0, left=0.0, right=0.0)
    hub.publish(np.zeros((8, 8, 3), dtype=np.uint8), clock_ns=t_video)
    monkeypatch.setattr("qoresence.monitor.frame_hub.get_frame_hub", lambda: hub)
    monkeypatch.setattr("qoresence.sync.input_ring.get_input_ring", lambda: ring)
    ivc = InputVideoCoupler(bus=None)
    payload = ivc.tick_once()
    assert payload is not None
    assert payload["phrase"] == "IDLE"
    assert payload["pll_lock"] is False
    assert not payload["coupling_ticket_id"]


def test_ivc_ema_rises_on_repeat(monkeypatch):
    hub = FrameHub()
    ring = InputRing()
    t_video = time.monotonic_ns()
    ring.set_hold(clock_ns=t_video, r2=0.95)
    hub.publish(np.zeros((8, 8, 3), dtype=np.uint8), clock_ns=t_video)
    monkeypatch.setattr("qoresence.monitor.frame_hub.get_frame_hub", lambda: hub)
    monkeypatch.setattr("qoresence.sync.input_ring.get_input_ring", lambda: ring)
    ivc = InputVideoCoupler(bus=None, ema_alpha=0.40)
    p1 = ivc.tick_once()
    # Refresh hold so it stays inside the 80 ms freshness window
    ring.set_hold(clock_ns=time.monotonic_ns(), r2=0.95)
    p2 = ivc.tick_once()
    assert p1 is not None and p2 is not None
    assert p1["coupling"] > 0.0
    assert p2["coupling_ema"] >= p1["coupling_ema"]
    assert p1["coupling_ema"] < p1["coupling"]
