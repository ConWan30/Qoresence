"""Unit tests for InputRing (no hardware)."""

from __future__ import annotations

import time

from qoresence.sync.input_ring import InputEvent, InputRing


def test_empty_window():
    ring = InputRing()
    assert ring.in_window(0, time.monotonic_ns()) == []
    assert ring.energy(0) == 0.0
    assert ring.latest_buttons() == []
    assert ring.snapshot(1.0) == []


def test_push_then_in_window():
    ring = InputRing()
    t0 = time.monotonic_ns()
    ring.push(InputEvent(clock_ns=t0 + 1000, kind="press", name="cross", value=1.0))
    ring.push(InputEvent(clock_ns=t0 + 2000, kind="release", name="cross", value=0.0))
    ring.push(InputEvent(clock_ns=t0 + 50_000_000, kind="press", name="r1", value=1.0))  # far

    hit = ring.in_window(t0, t0 + 10_000)
    assert len(hit) == 2
    assert hit[0].name == "cross"
    assert "cross" in [e.name for e in hit]


def test_energy_increases_on_press():
    ring = InputRing()
    t0 = time.monotonic_ns()
    e0 = ring.energy(t0 - 1)
    ring.push(InputEvent(clock_ns=t0, kind="press", name="square", value=1.0))
    e1 = ring.energy(t0 - 1)
    assert e1 > e0
    ring.push(InputEvent(clock_ns=t0 + 1, kind="trigger", name="R2", value=0.8))
    e2 = ring.energy(t0 - 1)
    assert e2 > e1


def test_latest_buttons_press_release():
    ring = InputRing()
    t = time.monotonic_ns()
    ring.push({"clock_ns": t, "kind": "press", "name": "triangle", "value": 1.0})
    assert "triangle" in ring.latest_buttons()
    ring.push({"clock_ns": t + 1, "kind": "release", "name": "triangle", "value": 0.0})
    assert "triangle" not in ring.latest_buttons()


def test_snapshot_seconds():
    ring = InputRing()
    t = time.monotonic_ns()
    ring.push(InputEvent(clock_ns=t, kind="press", name="l1", value=1.0))
    snap = ring.snapshot(seconds=2.0)
    assert len(snap) >= 1
    assert snap[0]["name"] == "l1"
    assert "kind" in snap[0]
