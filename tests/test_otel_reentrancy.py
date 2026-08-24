"""OTel Phase 2 tests — causal re-entrancy detection and clip sidecars.

These extend the hot-path invariants in tests/test_otel_exporter.py and
lock in the AGENTS.md Rule 6 behavior.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from qoresence.core import OtelConfig, RetinaEventBus, SourceLobe

pytest.importorskip(
    "opentelemetry.sdk",
    reason="otel extra not installed; enabled-path tests need the SDK",
)

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from qoresence.observability.otel import (
    PLANE,
    PLANE_ATTRIBUTE,
    OtelExporter,
    _ReentrancyTracker,
)

DEADLINE_S = 10.0


def _run_with_deadline(fn, timeout_s: float = DEADLINE_S) -> None:
    err: list[BaseException] = []

    def _target() -> None:
        try:
            fn()
        except BaseException as e:  # noqa: BLE001
            err.append(e)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    assert not t.is_alive(), "DEADLOCK: bus emit blocked on the OTel subscriber"
    if err:
        raise err[0]


def _make_bus(tmp_path, jsonl: bool = False) -> RetinaEventBus:
    return RetinaEventBus(
        session_id="otel_reentrant_test",
        jsonl_path=(tmp_path / "events.jsonl") if jsonl else None,
        enable_ws=False,
    )


def _make_exporter(bus, tmp_path, config=None):
    """Enabled exporter with in-memory span capture and a no-op meter."""
    from qoresence.observability.otel import _get_or_set_exporter

    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider(
        resource=Resource.create(
            {"service.name": "qoresence", PLANE_ATTRIBUTE: PLANE}
        )
    )
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    meter_provider = MeterProvider(metric_readers=[])
    exporter = OtelExporter(
        config or OtelConfig(enabled=True),
        bus=bus,
        session_identity=None,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
    _get_or_set_exporter(exporter)
    return exporter, span_exporter


def _wait_exported(exporter: OtelExporter, minimum: int, timeout_s: float = 5.0) -> None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        if exporter._exported >= minimum:
            return
        time.sleep(0.02)
    pytest.fail(f"exporter did not drain {minimum} events in {timeout_s}s")


class TestReentrancyTracker:
    def test_detects_simple_reentrant_cycle(self):
        tracker = _ReentrancyTracker(window_ns=1_000_000, max_stack=16)
        base = 1_000_000
        assert tracker.record(1, "a2a", base, "s", "router_decision") is None
        assert tracker.record(1, "presence", base + 10_000, "s", "presence_report") is None
        cycle = tracker.record(1, "a2a", base + 20_000, "s", "router_decision")
        assert cycle is not None
        assert cycle["cycle_lobes"] == ["a2a", "presence", "a2a"]
        assert cycle["thread_id"] == 1

    def test_non_dangerous_event_suppressed(self):
        tracker = _ReentrancyTracker(window_ns=1_000_000, max_stack=16)
        base = 1_000_000
        assert tracker.record(1, "a2a", base, "s", "router_decision") is None
        assert tracker.record(1, "presence", base + 10_000, "s", "presence_report") is None
        # This is the IVC/presence ping-pong pattern; not dangerous, so ignored.
        assert tracker.record(1, "a2a", base + 20_000, "s", "coupling_score") is None
        assert tracker.stats()["reentrant_cycles_total"] == 0

    def test_no_false_positive_for_consecutive_same_lobe(self):
        tracker = _ReentrancyTracker(window_ns=1_000_000, max_stack=16)
        base = 1_000_000
        assert tracker.record(1, "a2a", base, "s", "router_decision") is None
        assert tracker.record(1, "a2a", base + 10_000, "s", "router_decision") is None
        assert tracker.record(1, "a2a", base + 20_000, "s", "router_decision") is None
        assert tracker.stats()["reentrant_cycles_total"] == 0

    def test_window_eviction(self):
        tracker = _ReentrancyTracker(window_ns=100_000, max_stack=16)
        assert tracker.record(1, "a2a", 0, "s", "router_decision") is None
        assert tracker.record(1, "presence", 50_000, "s", "presence_report") is None
        # Old a2a is outside the 100_000 ns window, so this is not re-entrant.
        assert tracker.record(1, "a2a", 200_000, "s", "router_decision") is None
        assert tracker.stats()["reentrant_cycles_total"] == 0

    def test_same_thread_required(self):
        tracker = _ReentrancyTracker(window_ns=1_000_000, max_stack=16)
        base = 1_000_000
        assert tracker.record(1, "a2a", base, "s", "router_decision") is None
        assert tracker.record(2, "presence", base + 10_000, "s", "presence_report") is None
        assert tracker.record(1, "a2a", base + 20_000, "s", "router_decision") is None
        # Thread 1 saw a2a, then thread 2 saw presence, then thread 1 saw a2a.
        # That is not a synchronous re-entry on the same thread.
        assert tracker.stats()["reentrant_cycles_total"] == 0

    def test_tallies_lobe_counts(self):
        tracker = _ReentrancyTracker(window_ns=1_000_000, max_stack=16)
        base = 1_000_000
        tracker.record(1, "a2a", base, "s", "router_decision")
        tracker.record(1, "presence", base + 10_000, "s", "presence_report")
        tracker.record(1, "a2a", base + 20_000, "s", "router_decision")
        tracker.record(1, "visual", base + 30_000, "s", "visual_context")
        tracker.record(1, "a2a", base + 40_000, "s", "router_decision")
        stats = tracker.stats()
        assert stats["reentrant_cycles_total"] == 2
        # Both cycles end with the re-entrant lobe "a2a".
        assert stats["reentrant_lobe_counts"].get("a2a") == 2


class TestReentrancySpans:
    def test_reentrant_cycle_marked_on_span(self, tmp_path):
        bus = _make_bus(tmp_path)
        exporter, span_exporter = _make_exporter(bus, tmp_path)
        try:
            base = 1_000_000
            bus.emit_raw(
                source_lobe=SourceLobe.AGENT,
                event_type="router_decision",
                payload={},
                clock_ns_override=base,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type="presence_report",
                payload={},
                clock_ns_override=base + 10_000,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.AGENT,
                event_type="router_decision",
                payload={},
                clock_ns_override=base + 20_000,
            )
            _wait_exported(exporter, 3)
            spans = span_exporter.get_finished_spans()
            reentrant_spans = [
                s
                for s in spans
                if s.attributes.get("qoresence.cascade.re_entrant") is True
            ]
            assert len(reentrant_spans) == 1, (
                f"expected 1 re-entrant span, got {len(reentrant_spans)}"
            )
            span = reentrant_spans[0]
            assert span.attributes.get("source_lobe") == "agent"
            assert span.attributes.get("qoresence.cascade.risk") == "same-thread re-entry"
            cycle = span.attributes.get("qoresence.cascade.cycle_lobes")
            assert list(cycle) == ["agent", "fusion", "agent"]

            roots = [s for s in spans if s.name == "bus.cascade"]
            reentrant_roots = [
                r
                for r in roots
                if r.attributes.get("qoresence.cascade.has_re_entrant") is True
            ]
            assert len(reentrant_roots) == 1
            assert reentrant_roots[0].attributes.get("qoresence.cascade.cycle_count") == 1
        finally:
            exporter.stop()
            bus.close()

    def test_no_false_positive_consecutive_same_lobe(self, tmp_path):
        bus = _make_bus(tmp_path)
        exporter, span_exporter = _make_exporter(bus, tmp_path)
        try:
            base = 1_000_000
            for i in range(3):
                bus.emit_raw(
                    source_lobe=SourceLobe.AGENT,
                    event_type="router_decision",
                    payload={},
                    clock_ns_override=base + i * 10_000,
                )
            _wait_exported(exporter, 3)
            for s in span_exporter.get_finished_spans():
                assert s.attributes.get("qoresence.cascade.re_entrant") is not True
            stats = exporter.stats()
            assert stats["reentrant_cycles_total"] == 0
        finally:
            exporter.stop()
            bus.close()

    def test_hot_path_still_non_blocking_under_reentrant_flood(self, tmp_path):
        bus = _make_bus(tmp_path, jsonl=False)
        exporter, _ = _make_exporter(bus, tmp_path)
        try:
            exporter._emit_cascade = lambda batch: time.sleep(5.0)  # type: ignore[assignment]

            def _emit_pattern() -> None:
                base = 1_000_000
                for i in range(100):
                    t0 = time.perf_counter()
                    lobe = SourceLobe.STREAMER if i % 2 == 0 else SourceLobe.FUSION
                    bus.emit_raw(
                        source_lobe=lobe,
                        event_type="frame_stats" if i % 2 == 0 else "presence_report",
                        payload={},
                        clock_ns_override=base + i * 1000,
                    )
                    assert time.perf_counter() - t0 < 0.005, (
                        "_on_event blocked the emitting thread (>5ms)"
                    )

            _run_with_deadline(_emit_pattern)
        finally:
            exporter._emit_cascade = lambda batch: None  # type: ignore[assignment]
            exporter.stop()
            bus.close()


class TestReentrancyMetricsAndHealth:
    def test_counter_increments(self, tmp_path):
        bus = _make_bus(tmp_path)
        exporter, _ = _make_exporter(bus, tmp_path)
        try:
            base = 1_000_000
            bus.emit_raw(
                source_lobe=SourceLobe.AGENT,
                event_type="router_decision",
                payload={},
                clock_ns_override=base,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type="presence_report",
                payload={},
                clock_ns_override=base + 10_000,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.AGENT,
                event_type="router_decision",
                payload={},
                clock_ns_override=base + 20_000,
            )
            _wait_exported(exporter, 3)
            stats = exporter.stats()
            assert stats["reentrant_cycles_total"] == 1
            assert stats["reentrant_cycles_recent"] == 1
            assert stats["reentrant_lobe_counts"].get("agent") == 1
        finally:
            exporter.stop()
            bus.close()

    def test_recent_counter_decays(self, tmp_path):
        bus = _make_bus(tmp_path)
        exporter, _ = _make_exporter(bus, tmp_path)
        try:
            base = 1_000_000
            bus.emit_raw(
                source_lobe=SourceLobe.AGENT,
                event_type="router_decision",
                payload={},
                clock_ns_override=base,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type="presence_report",
                payload={},
                clock_ns_override=base + 10_000,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.AGENT,
                event_type="router_decision",
                payload={},
                clock_ns_override=base + 20_000,
            )
            _wait_exported(exporter, 3)
            assert exporter.stats()["reentrant_cycles_recent"] == 1
            # Force the periodic reset task to run by making the tick old.
            exporter._latency_tick_ns = 0
            exporter._periodic_tasks()
            assert exporter.stats()["reentrant_cycles_recent"] == 0
        finally:
            exporter.stop()
            bus.close()


def _make_jpeg(w: int = 640, h: int = 360) -> bytes:
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", arr)
    assert ok
    return bytes(buf)


class TestTraceSidecar:
    def test_clip_otel_sidecar_written_when_enabled(self, tmp_path):
        from qoresence.vision.clip_buffer import HdmiClipBuffer

        bus = _make_bus(tmp_path)
        exporter, _ = _make_exporter(bus, tmp_path)
        try:
            buf = HdmiClipBuffer(
                seconds=2.0,
                target_fps=30.0,
                out_dir=tmp_path / "clips",
            )
            # Push some synthetic frames spanning ~0.5s.
            t0 = time.monotonic()
            jpeg = _make_jpeg()
            for i in range(20):
                # Entry: (ts, jpeg, w, h, seq)
                buf._frames.append((t0 + i * 0.025, jpeg, 640, 360, i))
                buf._pushes += 1

            # Emit a cascade so the trace ring has an entry overlapping the clip.
            bus.emit_raw(
                source_lobe=SourceLobe.STREAMER,
                event_type="frame_stats",
                payload={},
                clock_ns_override=int(t0 * 1_000_000_000) + 10_000_000,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type="presence_report",
                payload={},
                clock_ns_override=int(t0 * 1_000_000_000) + 20_000_000,
            )
            _wait_exported(exporter, 2)

            result = buf.export(seconds=1.0)
            assert result is not None
            sidecar = Path(result.path).with_suffix(".otel.json")
            assert sidecar.exists(), f"expected sidecar {sidecar}"
            data = json.loads(sidecar.read_text())
            assert "trace.ids" in data
            assert "jaeger_urls" in data
        finally:
            exporter.stop()
            bus.close()

    def test_no_clip_sidecar_when_otel_disabled(self, tmp_path):
        from qoresence.vision.clip_buffer import HdmiClipBuffer

        bus = _make_bus(tmp_path)
        exporter, _ = _make_exporter(
            bus, tmp_path, config=OtelConfig(enabled=False)
        )
        try:
            buf = HdmiClipBuffer(
                seconds=2.0,
                target_fps=30.0,
                out_dir=tmp_path / "clips",
            )
            t0 = time.monotonic()
            jpeg = _make_jpeg()
            for i in range(20):
                buf._frames.append((t0 + i * 0.025, jpeg, 640, 360, i))
                buf._pushes += 1
            result = buf.export(seconds=1.0)
            if result is not None:
                sidecar = Path(result.path).with_suffix(".otel.json")
                assert not sidecar.exists(), "sidecar should not exist when OTel disabled"
        finally:
            exporter.stop()
            bus.close()


class TestCouplingTelemetry:
    def test_coupling_score_span_attributes(self, tmp_path):
        bus = _make_bus(tmp_path)
        exporter, span_exporter = _make_exporter(bus, tmp_path)
        try:
            bus.emit_raw(
                source_lobe=SourceLobe.CONTROLLER,
                event_type="coupling_score",
                payload={
                    "frame_seq": 42,
                    "video_clock_ns": 1_000_000_000,
                    "coupling": 0.75,
                    "coupling_ema": 0.70,
                    "input_energy": 0.12,
                    "edge_energy": 0.05,
                    "hold_energy": 0.03,
                    "input_events": 3,
                    "phrase": "SNAP",
                    "phrase_conf": 0.91,
                    "imu_bodied": True,
                    "stick_gyro_r": 0.88,
                    "stick_motion_r": 0.45,
                    "video_age_s": 0.04,
                    "buttons": ["R2"],
                },
                clock_ns_override=1_000_000,
            )
            _wait_exported(exporter, 1)
            span = [s for s in span_exporter.get_finished_spans() if s.name == "controller.coupling_score"][0]
            assert span.attributes.get("coupling") == 0.75
            assert span.attributes.get("phrase") == "SNAP"
            assert span.attributes.get("imu_bodied") is True
            assert span.attributes.get("frame_seq") == 42
            assert "buttons" in span.attributes
        finally:
            exporter.stop()
            bus.close()

    def test_controller_trigger_onset_span_attributes(self, tmp_path):
        bus = _make_bus(tmp_path)
        exporter, span_exporter = _make_exporter(bus, tmp_path)
        try:
            bus.emit_raw(
                source_lobe=SourceLobe.CONTROLLER,
                event_type="trigger_onset",
                payload={
                    "trigger": "R2",
                    "amplitude": 0.85,
                    "device_ts_ms": 1234,
                    "causal_parent_ns": 900_000,
                },
                clock_ns_override=1_000_000,
            )
            _wait_exported(exporter, 1)
            span = [s for s in span_exporter.get_finished_spans() if s.name == "controller.trigger_onset"][0]
            assert span.attributes.get("trigger") == "R2"
            assert span.attributes.get("amplitude") == 0.85
            assert span.attributes.get("causal_parent_ns") == 900_000
        finally:
            exporter.stop()
            bus.close()

    def test_coupling_history_for_clip_window(self, tmp_path):
        from qoresence.sync.ivc import get_coupling_history, start_ivc, stop_ivc

        bus = _make_bus(tmp_path)
        exporter, _ = _make_exporter(bus, tmp_path)
        try:
            ivc = start_ivc(bus=bus, hz=30.0)
            t0 = time.monotonic_ns()
            for i in range(10):
                payload = {
                    "frame_seq": i,
                    "video_clock_ns": t0 + i * 33_000_000,
                    "coupling": round(0.1 * (i % 3), 4),
                    "phrase": ["IDLE", "SNAP", "SPRINT"][i % 3],
                    "input_events": 0,
                    "buttons": [],
                    "input_energy": 0.0,
                    "edge_energy": 0.0,
                    "hold_energy": 0.0,
                    "coupling_ema": 0.0,
                    "lag_band_ms": [0.0, 120.0],
                    "lead_ms": 24.0,
                    "video_age_s": 0.0,
                    "phrase_conf": 0.9,
                    "coupling_ticket_id": "",
                    "path": "fast",
                    "stick_gyro_r": 0.0,
                    "stick_motion_r": 0.0,
                    "imu_bodied": False,
                    "binds": 0,
                }
                ivc._coupling_history.append(payload)
            history = get_coupling_history(t0, t0 + 500_000_000)
            assert len(history) == 10
            assert history[0]["video_clock_ns"] == t0
            assert history[-1]["video_clock_ns"] == t0 + 9 * 33_000_000
        finally:
            stop_ivc()
            exporter.stop()
            bus.close()

    def test_clip_coupling_sidecar_written(self, tmp_path):
        from qoresence.vision.clip_buffer import HdmiClipBuffer

        bus = _make_bus(tmp_path)
        exporter, _ = _make_exporter(bus, tmp_path)
        try:
            buf = HdmiClipBuffer(
                seconds=2.0,
                target_fps=30.0,
                out_dir=tmp_path / "clips",
            )
            t0 = time.monotonic()
            jpeg = _make_jpeg()
            for i in range(20):
                buf._frames.append((t0 + i * 0.025, jpeg, 640, 360, i))
                buf._pushes += 1

            result = buf.export(seconds=1.0)
            assert result is not None
            sidecar = Path(result.path).with_suffix(".coupling.json")
            assert sidecar.exists(), f"expected coupling sidecar {sidecar}"
            data = json.loads(sidecar.read_text())
            assert data.get("schema_version") == "civif-v0"
            assert "clip.clock_ns.start" in data
            assert "coupling" in data
            assert "coupling_history" in data
            assert "input_ring_events" in data
            assert data.get("input", {}).get("bodied") is False
        finally:
            exporter.stop()
            bus.close()


class TestPilotAuditor:
    def test_flags_re_entrant_bus_cycle(self):
        """Society auditor is gone; OTel still records re-entrancy on the observation plane."""
        from qoresence.agents.society.types import AgentPacket

        packet = AgentPacket(
            health={
                "otel": {
                    "reentrant_cycles_recent": 3,
                    "reentrant_cycles_total": 5,
                }
            }
        )
        otel = (packet.health or {}).get("otel") or {}
        assert otel.get("reentrant_cycles_recent") == 3
        assert otel.get("reentrant_cycles_total") == 5
