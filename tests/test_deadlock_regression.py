"""Deadlock regression tests — DO NOT DELETE OR WEAKEN.

These tests lock in the 2026-08 fix for a production freeze where the
whole live pipeline (streamer, watchdog, IVC) stalled and looked like a
dead capture card. Root cause was a synchronous event cascade:

    visual → ClutchBot → A2AOrchestrator.maybe_trigger_from_drive
      → bus.emit_raw(router_decision)              [emitted INSIDE self._lock]
      → PresenceFusionEngine._on_event             [holding presence RLock]
      → _emit_report → emit_raw(presence_report)   [still holding the RLock]
      → ClutchBot → maybe_trigger_from_drive again [same thread]
      → self._lock.acquire()                       → SELF-DEADLOCK

Every other thread then piled up behind the presence lock and the Deck froze.

Invariants enforced here (see AGENTS.md "Event bus locking rules"):
  1. A2AOrchestrator.maybe_trigger_from_drive must NEVER emit bus events
     while holding its internal lock, and must be re-entrancy safe on the
     same thread (thread-local guard).
  2. PresenceFusionEngine must NEVER hold its lock while fanning out to
     bus subscribers (_on_event / _emit_report emit outside the lock).
  3. Any subscriber may synchronously emit new events from its callback
     without deadlocking the bus.
"""

from __future__ import annotations

import threading
import time

from qoresence.a2a.orchestrator import A2AOrchestrator
from qoresence.core import (
    FusionWeights,
    RetinaEventBus,
    RetinaUnifiedConfig,
    SessionAuthority,
    SourceLobe,
    StreamerConfig,
)
from qoresence.fusion.presence import PresenceFusionEngine

# Any single emit must complete well under this bound; a deadlock never does.
DEADLOCK_TIMEOUT_S = 10.0


def _wait_inflight_clear(orch: A2AOrchestrator, timeout_s: float = 5.0) -> None:
    """Let background a2a-cycle threads finish so temp files are not busy."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        with orch._lock:
            if not orch._inflight:
                return
        time.sleep(0.05)


def _run_with_deadline(fn, timeout_s: float = DEADLOCK_TIMEOUT_S) -> None:
    """Run fn in a thread; fail the test if it doesn't finish (deadlock)."""
    err: list[BaseException] = []

    def _target() -> None:
        try:
            fn()
        except BaseException as e:  # noqa: BLE001 — surface into main thread
            err.append(e)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    assert not t.is_alive(), (
        "DEADLOCK REGRESSION: event cascade did not complete. "
        "Someone reintroduced an emit-while-holding-lock in "
        "A2AOrchestrator.maybe_trigger_from_drive or PresenceFusionEngine."
    )
    if err:
        raise err[0]


class TestA2ARouterDecisionCascade:
    """maybe_trigger_from_drive must survive its own emit cascading back in."""

    def _make_orchestrator(self, bus: RetinaEventBus) -> A2AOrchestrator:
        orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)
        orch.bus.set_retina_mirror(bus, session_id="deadlock_test")
        return orch

    def _football_situation(self) -> dict:
        return {"game_category": "football", "game_state": "gameplay"}

    def test_reentrant_trigger_from_router_decision_does_not_deadlock(self, tmp_path):
        """Simulates ClutchBot re-triggering A2A from the router_decision emit."""
        bus = RetinaEventBus(
            session_id="deadlock_test",
            jsonl_path=tmp_path / "events.jsonl",
            enable_ws=False,
        )
        orch = self._make_orchestrator(bus)

        def _reenter(event) -> None:
            # Mimic ClutchBot: every router_decision event immediately
            # asks for another A2A trigger on the SAME thread.
            if event.type == "router_decision":
                orch.maybe_trigger_from_drive(
                    situation=self._football_situation(),
                    coupling=1.0,
                    reason="coupling",
                )

        bus.subscribe(_reenter)

        _run_with_deadline(
            lambda: orch.maybe_trigger_from_drive(
                situation=self._football_situation(),
                coupling=1.0,
                reason="coupling",
            )
        )
        _wait_inflight_clear(orch)
        bus.close()

    def test_suppressed_trigger_emits_outside_lock(self, tmp_path):
        """Even interval/in-flight-suppressed decisions must not emit under the lock."""
        bus = RetinaEventBus(
            session_id="deadlock_test2",
            jsonl_path=tmp_path / "events.jsonl",
            enable_ws=False,
        )
        orch = self._make_orchestrator(bus)
        orch._inflight = True  # force the suppressed path

        lock_free_during_emit: list[bool] = []

        def _probe(event) -> None:
            if event.type == "router_decision":
                # If the orchestrator lock is held during fan-out, this
                # non-blocking acquire fails → regression.
                got = orch._lock.acquire(blocking=False)
                if got:
                    orch._lock.release()
                lock_free_during_emit.append(got)

        bus.subscribe(_probe)

        _run_with_deadline(
            lambda: orch.maybe_trigger_from_drive(
                situation=self._football_situation(),
                coupling=1.0,
                reason="coupling",
            )
        )
        assert lock_free_during_emit and all(lock_free_during_emit), (
            "router_decision was emitted while A2AOrchestrator._lock was "
            "held — this recreates the 2026-08 live freeze."
        )
        bus.close()


class TestPresenceFusionLockDiscipline:
    """Presence fusion must not hold its lock during bus fan-out."""

    def _make_engine(self, bus: RetinaEventBus) -> PresenceFusionEngine:
        identity = SessionAuthority.mint(session_id="deadlock_test3")
        config = RetinaUnifiedConfig(
            session_id="deadlock_test3",
            session_head_ns=identity.session_head_ns,
            fusion_weights=FusionWeights(),
            streamer=StreamerConfig(enabled=True),
        )
        return PresenceFusionEngine(config, bus)

    def test_presence_lock_released_during_report_fanout(self, tmp_path):
        bus = RetinaEventBus(
            session_id="deadlock_test3",
            jsonl_path=tmp_path / "events.jsonl",
            enable_ws=False,
        )
        engine = self._make_engine(bus)
        try:
            blocked: list[float] = []

            def _cross_thread_probe(event) -> None:
                if event.type != "presence_report":
                    return
                # From ANOTHER thread, try to take the presence lock while
                # this subscriber callback runs. RLock re-entry on the same
                # thread would mask the bug, so probe cross-thread.
                t0 = time.monotonic()

                def _acquire() -> None:
                    with engine._lock:
                        pass

                t = threading.Thread(target=_acquire, daemon=True)
                t.start()
                t.join(timeout=2.0)
                blocked.append(time.monotonic() - t0)
                assert not t.is_alive(), (
                    "PresenceFusionEngine held its lock during "
                    "presence_report fan-out — other lobes would stall."
                )

            bus.subscribe(_cross_thread_probe)

            _run_with_deadline(
                lambda: bus.emit_raw(
                    source_lobe=SourceLobe.STREAMER,
                    event_type="frame_stats",
                    payload={"n": 1},
                )
            )
            assert blocked, "presence_report was never emitted"
        finally:
            engine.stop()
            bus.close()

    def test_full_cascade_streamer_event_with_a2a_loop(self, tmp_path):
        """End-to-end: streamer emit → presence report → A2A trigger →
        router_decision → presence report → ... must terminate quickly."""
        bus = RetinaEventBus(
            session_id="deadlock_test4",
            jsonl_path=tmp_path / "events.jsonl",
            enable_ws=False,
        )
        engine = self._make_engine(bus)
        orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)
        orch.bus.set_retina_mirror(bus, session_id="deadlock_test4")
        try:

            def _clutchbot_like(event) -> None:
                if event.type in ("presence_report", "router_decision"):
                    orch.maybe_trigger_from_drive(
                        situation={
                            "game_category": "football",
                            "game_state": "gameplay",
                        },
                        coupling=1.0,
                        reason="coupling",
                    )

            bus.subscribe(_clutchbot_like)

            # This exact emit pattern froze the live session pre-fix.
            _run_with_deadline(
                lambda: bus.emit_raw(
                    source_lobe=SourceLobe.STREAMER,
                    event_type="zone_trigger",
                    payload={"zone": "test", "state": "active"},
                )
            )
            _wait_inflight_clear(orch)
        finally:
            engine.stop()
            bus.close()


class TestJsonlSinkPersistentHandle:
    """The JSONL sink must keep one append handle, not open/close per emit.

    Regression for the 2026-08-16 incident: a 432 MB soak file caused every
    lobe to block in ``pathlib.open`` under ``_jsonl_lock`` on each emit,
    wedging the Deck /health endpoint. The fix is a persistent append handle
    with per-write flush (same durability, no per-emit open syscall).
    """

    def test_handle_reused_across_emits(self, tmp_path):
        bus = RetinaEventBus(
            session_id="jsonl_sink_test",
            jsonl_path=tmp_path / "events.jsonl",
            enable_ws=False,
        )
        try:
            bus.emit_raw(
                source_lobe=SourceLobe.STREAMER,
                event_type="frame_stats",
                payload={"n": 1},
            )
            first_fh = bus._jsonl_fh
            assert first_fh is not None, "handle should be open after first emit"
            assert not first_fh.closed
            # Many more emits must reuse the SAME handle (no per-emit open).
            for i in range(200):
                bus.emit_raw(
                    source_lobe=SourceLobe.STREAMER,
                    event_type="frame_stats",
                    payload={"n": i},
                )
            assert bus._jsonl_fh is first_fh, (
                "JSONL handle was reopened mid-stream — per-emit open() is the "
                "wedge bug; the handle must persist for the life of the bus."
            )
            assert not first_fh.closed
            # All events landed on disk (per-write flush).
            lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
            assert len(lines) == 201
        finally:
            bus.close()
        assert bus._jsonl_fh is None, "close() must release the handle"

    def test_close_releases_file_for_tmp_cleanup(self, tmp_path):
        bus = RetinaEventBus(
            session_id="jsonl_sink_close_test",
            jsonl_path=tmp_path / "events.jsonl",
            enable_ws=False,
        )
        bus.emit_raw(
            source_lobe=SourceLobe.STREAMER,
            event_type="frame_stats",
            payload={"n": 1},
        )
        bus.close()
        # After close, the file must be writable/truncatable by the OS — i.e.
        # no lingering handle. This is what lets pytest clean up tmp_path on
        # Windows and what lets a new session re-open the soak path.
        (tmp_path / "events.jsonl").write_text("ok", encoding="utf-8")


class TestStreamerWatchdogLockRelease:
    """Streamer watchdog must not emit or rebind while holding self._lock.

    Production freeze (2026-08-22): watchdog held the streamer RLock across
    heartbeat fan-out and DShow release/reopen. The capture loop then blocked
    on ``_last_success_frame_time`` updates, ``age_s`` climbed, and /health
    timed out. See AGENTS.md Rule 1.
    """

    def test_watchdog_tick_does_not_hold_lock_during_emit_or_rebind(self, tmp_path):
        from qoresence.lobes.streamer import StreamerRuntime

        bus = RetinaEventBus(
            session_id="watchdog_lock_test",
            jsonl_path=tmp_path / "events.jsonl",
            enable_ws=False,
        )
        identity = SessionAuthority.mint(session_id="watchdog_lock_test")
        runtime = StreamerRuntime(
            config=StreamerConfig(enabled=True, device_index=0, eye_check_required=False),
            bus=bus,
            session_head_ns=identity.session_head_ns,
        )
        runtime._last_success_frame_time = time.time() - 10.0
        peer_got_lock: list[bool] = []

        def _peer_try_lock() -> None:
            ok = runtime._lock.acquire(blocking=False)
            peer_got_lock.append(ok)
            if ok:
                runtime._lock.release()

        def _probe(_now: float | None = None) -> bool:
            t = threading.Thread(target=_peer_try_lock)
            t.start()
            t.join()
            return False

        runtime._emit_heartbeat = _probe  # type: ignore[method-assign]
        runtime._try_rebind_capture = _probe  # type: ignore[method-assign]
        runtime._watchdog_tick(time.time())
        assert peer_got_lock == [True, True], (
            "DEADLOCK/FREEZE REGRESSION: watchdog held streamer lock during "
            f"heartbeat/rebind — peer acquire results={peer_got_lock}"
        )
        bus.close()


class TestStemConductorEmitOutsideLock:
    """stem_program must be emitted after the conductor lock is released."""

    def test_reentrant_stem_program_does_not_deadlock(self, tmp_path):
        from qoresence.core import EventType, SourceLobe
        from qoresence.stem.conductor import StemConductor

        bus = RetinaEventBus(
            session_id="stem_deadlock",
            jsonl_path=tmp_path / "events.jsonl",
            enable_ws=False,
        )
        cond = StemConductor(bus)
        hits: list[int] = []

        def _reenter(event) -> None:
            if getattr(event.type, "value", event.type) != EventType.STEM_PROGRAM.value:
                return
            hits.append(1)
            cond.note_clip_busy(False)

        bus.subscribe(_reenter)
        try:
            _run_with_deadline(lambda: cond.note_clip_busy(True))
            assert hits, "stem_program was never emitted"
            assert SourceLobe.STEM.value == "stem"
        finally:
            cond.stop()
            bus.close()


class TestFrameHubHidHotPlug:
    """USB Edge plug / HID ingest must not freeze FrameHub.publish (grab path)."""

    def test_framehub_publish_and_hid_ingest_do_not_deadlock(self, tmp_path):
        import numpy as np

        from qoresence.core import ControllerConfig
        from qoresence.lobes.controller import ControllerRuntime
        from qoresence.monitor.frame_hub import FrameHub
        from qoresence.sync.hid_report import CROSS, pack_usb_report

        bus = RetinaEventBus(
            session_id="hid_hotplug",
            jsonl_path=tmp_path / "events.jsonl",
            enable_ws=False,
        )

        def _slow_sub(event) -> None:
            time.sleep(0.002)

        bus.subscribe(_slow_sub)
        hub = FrameHub()
        runtime = ControllerRuntime(
            config=ControllerConfig(enabled=True),
            bus=bus,
            session_head_ns=0,
        )
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        report = pack_usb_report(buttons=CROSS)

        def _work() -> None:
            for i in range(8):
                hub.publish(frame, clock_ns=time.monotonic_ns(), seq=i + 1)
                runtime.ingest_report(report, host_ts_ns=time.monotonic_ns())

        try:
            _run_with_deadline(_work)
            assert hub.get_latest_stamp()["has_frame"]
            assert runtime.get_stats()["reports"] >= 8
        finally:
            bus.close()
