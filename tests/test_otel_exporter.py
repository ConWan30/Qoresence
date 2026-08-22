"""OTel exporter tests — hot-path safety, flood, short cascades, plane attr.

The exporter is an observation-plane bus subscriber. The critical invariant
(same family as tests/test_deadlock_regression.py): ``_on_event`` runs
synchronously on the emitting thread and must ONLY enqueue — a stalled
exporter must never stall the bus.
"""

from __future__ import annotations

import threading
import time

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
    make_otel_exporter_from_config,
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


def _make_exporter(bus, tmp_path):
    """Enabled exporter with in-memory span capture and a no-op meter."""
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider(
        resource=Resource.create({"service.name": "qoresence", PLANE_ATTRIBUTE: PLANE})
    )
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    meter_provider = MeterProvider(metric_readers=[])
    exporter = OtelExporter(
        OtelConfig(enabled=True),
        bus=bus,
        session_identity=None,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
    return exporter, span_exporter


def _make_bus(tmp_path) -> RetinaEventBus:
    return RetinaEventBus(
        session_id="otel_test",
        jsonl_path=tmp_path / "events.jsonl",
        enable_ws=False,
    )


def _wait_exported(exporter: OtelExporter, minimum: int, timeout_s: float = 5.0) -> None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        if exporter._exported >= minimum:
            return
        time.sleep(0.02)
    pytest.fail(f"exporter did not drain {minimum} events in {timeout_s}s")


class TestConstruction:
    def test_disabled_config_constructs_disabled(self, tmp_path):
        exporter = OtelExporter(OtelConfig(enabled=False))
        assert exporter.enabled is False
        assert exporter.stats() == {
            "enabled": False,
            "exported": 0,
            "dropped": 0,
            "last_export_ns": 0,
            "reentrant_cycles_total": 0,
            "reentrant_cycles_recent": 0,
            "reentrant_lobe_counts": {},
            "recent_cycles": [],
        }

    def test_factory_returns_none_when_disabled(self, tmp_path):
        assert make_otel_exporter_from_config(OtelConfig(enabled=False)) is None

    def test_missing_extra_disables_without_raising(self, tmp_path, monkeypatch):
        # Simulate the otel extra being absent: break the lazy import.
        import builtins

        real_import = builtins.__import__

        def _blocked(name, *a, **k):
            if name.startswith("opentelemetry"):
                raise ImportError(f"no module named {name!r} (simulated)")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", _blocked)
        exporter = OtelExporter(OtelConfig(enabled=True), bus=None)
        assert exporter.enabled is False


class TestSpansAndStats:
    def test_events_become_spans_with_plane_attribute(self, tmp_path):
        bus = _make_bus(tmp_path)
        exporter, span_exporter = _make_exporter(bus, tmp_path)
        try:
            bus.emit_raw(
                source_lobe=SourceLobe.STREAMER,
                event_type="frame_stats",
                payload={"n": 1, "frame_seq": 7, "fps": 29.5},
                clock_ns_override=1_000_000,
            )
            bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type="presence_report",
                payload={},
                clock_ns_override=1_100_000,
            )
            _wait_exported(exporter, 2)
            spans = span_exporter.get_finished_spans()
            names = {s.name for s in spans}
            assert "streamer.frame_stats" in names
            assert "fusion.presence_report" in names
            for s in spans:
                assert s.attributes.get("plane") == "qoresence-observation"
                assert s.resource.attributes.get("plane") == "qoresence-observation"
                if s.name != "bus.cascade":
                    assert s.attributes.get("session_id") == "otel_test"
            stats = exporter.stats()
            assert stats["enabled"] is True
            assert stats["exported"] >= 2
            assert stats["last_export_ns"] > 0
        finally:
            exporter.stop()
            bus.close()

    def test_no_payload_dumped_into_attributes(self, tmp_path):
        bus = _make_bus(tmp_path)
        exporter, span_exporter = _make_exporter(bus, tmp_path)
        try:
            secret = "SUPERSECRET-TICKET-TEXT"
            bus.emit_raw(
                source_lobe=SourceLobe.OUTCOME,
                event_type="outcome_event",
                payload={"ticket": secret, "score_text": secret * 20},
                clock_ns_override=1_000_000,
            )
            _wait_exported(exporter, 1)
            for s in span_exporter.get_finished_spans():
                for v in s.attributes.values():
                    assert secret not in str(v)
        finally:
            exporter.stop()
            bus.close()

    def test_traces_are_short_cascades_not_mega_trace(self, tmp_path):
        bus = _make_bus(tmp_path)
        exporter, span_exporter = _make_exporter(bus, tmp_path)
        try:
            # 200 tightly-grouped events — cascade_max_events=64 forces at
            # least 4 separate short traces, never one giant tree.
            def _flood() -> None:
                base = 1_000_000
                for i in range(200):
                    bus.emit_raw(
                        source_lobe=SourceLobe.STREAMER,
                        event_type="frame_stats",
                        payload={"n": i},
                        clock_ns_override=base + i * 1000,
                    )

            _run_with_deadline(_flood)
            _wait_exported(exporter, 200, timeout_s=10.0)
            spans = span_exporter.get_finished_spans()
            trace_ids = {s.context.trace_id for s in spans}
            assert len(trace_ids) >= 3, (
                f"expected multiple short cascade traces, got {len(trace_ids)}"
            )
            roots = [s for s in spans if s.parent is None]
            for r in roots:
                assert r.attributes.get("events", 0) <= 64
        finally:
            exporter.stop()
            bus.close()


class TestHotPathSafety:
    def test_on_event_never_blocks_with_stalled_worker(self, tmp_path):
        bus = _make_bus(tmp_path)
        exporter, _ = _make_exporter(bus, tmp_path)
        try:
            # Stall the drain path: the exporter is as slow as it can be.
            exporter._emit_cascade = lambda batch: time.sleep(5.0)  # type: ignore[assignment]

            def _emit_ten() -> None:
                for i in range(10):
                    t0 = time.perf_counter()
                    bus.emit_raw(
                        source_lobe=SourceLobe.STREAMER,
                        event_type="frame_stats",
                        payload={"n": i},
                        clock_ns_override=1_000_000 + i * 1000,
                    )
                    assert time.perf_counter() - t0 < 0.05, (
                        "_on_event blocked the emitting thread (>50ms)"
                    )

            _run_with_deadline(_emit_ten)
        finally:
            exporter._emit_cascade = lambda batch: None  # type: ignore[assignment]
            exporter.stop()
            bus.close()

    def test_flood_10k_no_deadlock_and_drops(self, tmp_path):
        bus = _make_bus(tmp_path)
        exporter, _ = _make_exporter(bus, tmp_path)
        try:
            exporter._emit_cascade = lambda batch: time.sleep(2.0)  # type: ignore[assignment]

            def _flood() -> None:
                base = 1_000_000
                for i in range(10_000):
                    bus.emit_raw(
                        source_lobe=SourceLobe.STREAMER,
                        event_type="frame_stats",
                        payload={"n": i},
                        clock_ns_override=base + i * 1000,
                    )

            _run_with_deadline(_flood, timeout_s=30.0)
            # The queue (2048) cannot hold 10k stalled events → drops, not blocks.
            exporter._emit_cascade = lambda batch: None  # type: ignore[assignment]
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and exporter._dropped == 0:
                time.sleep(0.02)
            assert exporter._dropped > 0 or exporter.stats()["dropped"] > 0, (
                "expected drop-oldest under flood (queue should have overflowed)"
            )
        finally:
            exporter._emit_cascade = lambda batch: None  # type: ignore[assignment]
            exporter.stop()
            bus.close()


class TestBusCascadeWithExporter:
    """The full deadlock-regression cascade must stay green with the OTel
    exporter subscribed alongside presence + A2A (see test_deadlock_regression)."""

    def test_full_cascade_completes_with_otel_subscribed(self, tmp_path):
        from qoresence.a2a.orchestrator import A2AOrchestrator
        from qoresence.core import (
            FusionWeights,
            RetinaUnifiedConfig,
            SessionAuthority,
            StreamerConfig,
        )
        from qoresence.fusion.presence import PresenceFusionEngine

        bus = RetinaEventBus(
            session_id="otel_cascade_test",
            jsonl_path=tmp_path / "events.jsonl",
            enable_ws=False,
        )
        exporter, _ = _make_exporter(bus, tmp_path)

        identity = SessionAuthority.mint(session_id="otel_cascade_test")
        config = RetinaUnifiedConfig(
            session_id="otel_cascade_test",
            session_head_ns=identity.session_head_ns,
            fusion_weights=FusionWeights(),
            streamer=StreamerConfig(enabled=True),
        )
        engine = PresenceFusionEngine(config, bus)
        orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)
        orch.bus.set_retina_mirror(bus, session_id="otel_cascade_test")
        try:

            def _clutchbot_like(event) -> None:
                if event.type in ("presence_report", "router_decision"):
                    orch.maybe_trigger_from_drive(
                        situation={"game_category": "football", "game_state": "gameplay"},
                        coupling=1.0,
                        reason="coupling",
                    )

            bus.subscribe(_clutchbot_like)

            def _emit() -> None:
                bus.emit_raw(
                    source_lobe=SourceLobe.STREAMER,
                    event_type="zone_trigger",
                    payload={"zone": "test", "state": "active"},
                )

            _run_with_deadline(_emit)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 5.0:
                with orch._lock:
                    if not orch._inflight:
                        break
                time.sleep(0.05)
        finally:
            engine.stop()
            exporter.stop()
            bus.close()
