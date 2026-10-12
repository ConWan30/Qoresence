"""Capture rebind race (Madden pilot crash 2026-10-11).

Symptoms on the laptop: video stalled, two "Capture device rebound" lines,
"Failed to open capture source 0" (device busy), then python.exe 0xc0000005
in ntdll. Mechanism reproduced here with fake captures (no hardware):

* run loop (30 failed grabs) and watchdog (8 s stall) both called
  ``_try_rebind_capture`` at ~the same time; the 3 s throttle was a
  check-then-set race, so two rebinds ran concurrently and opened the
  DShow device twice;
* a rebind released the VideoCapture while the grabber (or a timed read) was
  still inside native ``read()`` — use-after-free;
* the shared grab stop Event was ``clear()``-ed by the next grabber, reviving
  an abandoned grabber so two threads read one capture.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

import numpy as np

from qoresence.core import RetinaEventBus, SessionAuthority, StreamerConfig
from qoresence.lobes.streamer import GuardedCapture, StreamerRuntime


class NativeLikeCapture:
    """Fake native capture that records unsafe use instead of segfaulting."""

    def __init__(self, name: str = "cap", hang: bool = False) -> None:
        self.name = name
        self.gate = threading.Event()
        if not hang:
            self.gate.set()
        self.in_read = 0
        self.max_concurrent_reads = 0
        self.reads = 0
        self.release_calls = 0
        self.violations: list[str] = []
        self.set_calls = 0
        self._mu = threading.Lock()

    def read(self):
        with self._mu:
            if self.release_calls:
                self.violations.append("read_after_release")
            self.in_read += 1
            self.reads += 1
            self.max_concurrent_reads = max(self.max_concurrent_reads, self.in_read)
        try:
            self.gate.wait(5.0)
            time.sleep(0.005)
            return True, np.full((72, 128, 3), 90, dtype=np.uint8)
        finally:
            with self._mu:
                self.in_read -= 1

    def release(self) -> None:
        with self._mu:
            if self.in_read:
                self.violations.append("release_during_read")
            self.release_calls += 1

    def isOpened(self) -> bool:  # noqa: N802
        return self.release_calls == 0

    def set(self, prop, value) -> bool:
        with self._mu:
            if self.in_read:
                self.violations.append("set_during_read")
            self.set_calls += 1
        return True

    def get(self, prop) -> float:
        return 30.0


def _runtime() -> tuple[StreamerRuntime, RetinaEventBus, tempfile.TemporaryDirectory]:
    td = tempfile.TemporaryDirectory()
    bus = RetinaEventBus(
        session_id="rebind_race", jsonl_path=Path(td.name) / "e.jsonl", enable_ws=False
    )
    ident = SessionAuthority.mint(session_id="rebind_race")
    rt = StreamerRuntime(
        config=StreamerConfig(enabled=True, device_index=0, eye_check_required=False),
        bus=bus,
        session_head_ns=ident.session_head_ns,
    )
    rt._emit_heartbeat = lambda _now: None  # type: ignore[method-assign]
    return rt, bus, td


# ── GuardedCapture ─────────────────────────────────────────────────────────


def test_release_during_read_is_deferred_to_reader():
    raw = NativeLikeCapture(hang=True)
    g = GuardedCapture(raw)
    t = threading.Thread(target=g.read)
    t.start()
    while not g.read_in_flight:
        time.sleep(0.001)
    assert g.release() is False  # deferred, not released under the read
    assert raw.release_calls == 0
    assert g.isOpened() is False
    raw.gate.set()
    t.join(2.0)
    assert raw.release_calls == 1
    assert raw.violations == []
    # Further reads never touch the native handle.
    assert g.read() == (False, None)
    assert raw.reads == 1
    assert g.release() is True
    assert raw.release_calls == 1


def test_concurrent_read_never_enters_native_twice():
    raw = NativeLikeCapture(hang=True)
    g = GuardedCapture(raw)
    t = threading.Thread(target=g.read)
    t.start()
    while not g.read_in_flight:
        time.sleep(0.001)
    assert g.read() == (False, None)
    raw.gate.set()
    t.join(2.0)
    assert raw.max_concurrent_reads == 1


def test_set_during_hung_read_is_skipped():
    raw = NativeLikeCapture(hang=True)
    g = GuardedCapture(raw)
    t = threading.Thread(target=g.read)
    t.start()
    while not g.read_in_flight:
        time.sleep(0.001)
    t0 = time.monotonic()
    assert g.set(5, 15.0) is False
    assert time.monotonic() - t0 < 1.5
    raw.gate.set()
    t.join(2.0)
    assert raw.violations == []
    assert g.set(5, 15.0) is True


# ── Single-flight rebind ───────────────────────────────────────────────────


def test_concurrent_rebind_is_single_flight():
    """Run loop + watchdog rebinding together must open the device once.

    A real rebind (1.5 s grabber join + DShow enumerate + 2 s first-frame
    read) outlives the 3 s throttle, so the second caller used to sail past it
    and open the device while the first was still mid-open.
    """
    rt, bus, td = _runtime()
    rt._resolve_device = lambda: (0, "USB3.0 Video")  # type: ignore[method-assign]
    state = {"inside": 0, "max": 0, "opens": 0}
    mu = threading.Lock()
    first_inside = threading.Event()

    def _slow_open() -> bool:
        with mu:
            state["inside"] += 1
            state["opens"] += 1
            state["max"] = max(state["max"], state["inside"])
        first_inside.set()
        time.sleep(0.4)
        rt._cap = GuardedCapture(NativeLikeCapture("new"))
        with mu:
            state["inside"] -= 1
        return True

    rt._open_capture = _slow_open  # type: ignore[method-assign]
    results: list[bool] = []
    a = threading.Thread(target=lambda: results.append(rt._try_rebind_capture()))
    a.start()
    assert first_inside.wait(2.0)
    rt._last_rebind_attempt -= 10.0  # the slow open has outlived the 3 s throttle
    b = threading.Thread(target=lambda: results.append(rt._try_rebind_capture()))
    b.start()
    a.join(5.0)
    b.join(5.0)
    assert state["max"] == 1, "two rebinds opened the DShow device concurrently"
    assert state["opens"] == 1
    assert sorted(results) == [False, True]
    assert rt._rebinds_skipped_inflight == 1
    rt._detach_capture()
    bus.close()
    td.cleanup()


def test_rebind_throttle_counts_from_end_of_attempt():
    rt, bus, td = _runtime()
    rt._resolve_device = lambda: (0, "USB3.0 Video")  # type: ignore[method-assign]

    def _slow_fail() -> bool:
        time.sleep(0.2)
        return False

    rt._open_capture = _slow_fail  # type: ignore[method-assign]
    assert rt._try_rebind_capture() is False
    end = time.time()
    assert rt._last_rebind_attempt >= end - 0.05
    bus.close()
    td.cleanup()


def test_hung_read_rebind_never_releases_under_read_and_no_double_reader():
    """The crash path: grabber stuck in read() while run loop + watchdog rebind."""
    rt, bus, td = _runtime()
    old_raw = NativeLikeCapture("old", hang=True)
    rt._cap = GuardedCapture(old_raw)
    rt._start_grabber()
    while old_raw.in_read == 0:
        time.sleep(0.001)

    new_raw = NativeLikeCapture("new")
    rt._resolve_device = lambda: (0, "USB3.0 Video")  # type: ignore[method-assign]

    def _open() -> bool:
        rt._cap = GuardedCapture(new_raw)
        rt._start_grabber()
        return True

    rt._open_capture = _open  # type: ignore[method-assign]
    barrier = threading.Barrier(2)
    results: list[bool] = []

    def _caller() -> None:
        barrier.wait()
        results.append(rt._try_rebind_capture())

    ts = [threading.Thread(target=_caller) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(6.0)
    assert sorted(results) == [False, True]
    # Old handle is still held by the stuck read: not released under it.
    assert old_raw.release_calls == 0
    # Unhang the old read: the stale grabber must exit, release the old
    # handle itself, and never touch the new capture.
    old_raw.gate.set()
    time.sleep(0.3)
    assert old_raw.release_calls == 1
    assert old_raw.violations == []
    assert old_raw.reads == 1
    assert new_raw.max_concurrent_reads == 1
    assert new_raw.violations == []
    ok, frame = rt._read_frame()
    assert ok and frame is not None
    rt._detach_capture()
    assert new_raw.release_calls == 1
    assert new_raw.violations == []
    bus.close()
    td.cleanup()


def test_timed_read_timeout_defers_release():
    rt, bus, td = _runtime()
    raw = NativeLikeCapture(hang=True)
    g = GuardedCapture(raw)
    rt._cap = g
    ok, frame = rt._timed_read(g, timeout=0.1)
    assert (ok, frame) == (False, None)
    assert rt._cap is None
    assert raw.release_calls == 0
    raw.gate.set()
    time.sleep(0.2)
    assert raw.release_calls == 1
    assert raw.violations == []
    bus.close()
    td.cleanup()


def test_stop_during_hung_read_does_not_release_under_read():
    rt, bus, td = _runtime()
    raw = NativeLikeCapture(hang=True)
    rt._cap = GuardedCapture(raw)
    rt._start_grabber()
    while raw.in_read == 0:
        time.sleep(0.001)
    rt.stop()
    assert raw.violations == []
    assert raw.release_calls == 0
    raw.gate.set()
    time.sleep(0.2)
    assert raw.release_calls == 1
    assert raw.violations == []
    bus.close()
    td.cleanup()
