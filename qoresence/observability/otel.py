"""Opt-in OpenTelemetry exporter for Qoresence (observation plane only).

Exports bus-cascade traces and capture-health metrics over OTLP gRPC to a
local Collector (default ``http://127.0.0.1:4317``). Enable with ``--otel``
or ``QORESENCE_OTEL=1``. Default OFF.

Phase 2 adds causal re-entrancy detection: we track the per-thread sequence
of ``source_lobe`` events as the bus fans out. When the same lobe appears
twice on the same OS thread with at least one different lobe between, the
cascade is a re-entry candidate (the same failure family as the 2026-08
event-loop deadlock in ``AGENTS.md``).

HARD RULES (same class as the AGENTS.md event-bus locking rules):

1. ``_on_event`` runs synchronously on the emitting thread — it must ONLY
   enqueue (bounded queue, drop-oldest). Never block, never emit bus events,
   never acquire a lobe lock.
2. No payload dumps. Only small scalar attributes (session_id, source_lobe,
   event_type, clock_ns, frame_seq, capture-health scalars, thread_id).
3. No session-long mega-trace. Traces are short cascades: a bounded group of
   events within one ``clock_ns`` window becomes one small trace tree.
4. Every resource and span carries ``plane=qoresence-observation``.
5. The re-entrancy tracker is observation-only. It may record cycles and
   write small anomaly JSONL entries; it must never take a lobe lock, never
   emit bus events, and never block the worker on network or disk.

See docs/OTEL.md.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from qoresence.core import BaseEvent

log = logging.getLogger(__name__)

PLANE_ATTRIBUTE = "plane"
PLANE = "qoresence-observation"

# Small scalar keys lifted from event payloads into the queue record (and
# from there into gauges). Anything else in the payload is ignored.
_VIDEO_KEYS = ("age_s", "frames", "pushes", "fps")

# Coupling / controller telemetry scalars. "phrase" is used as a span and
# metric attribute; it has low cardinality (IDLE, SNAP, SPRINT, ...).
_COUPLING_KEYS = (
    "coupling",
    "coupling_ema",
    "input_energy",
    "edge_energy",
    "hold_energy",
    "input_events",
    "video_age_s",
    "phrase",
    "phrase_conf",
    "imu_bodied",
    "buttons",
    "stick_gyro_r",
    "stick_motion_r",
    "frame_seq",
    "video_clock_ns",
)

# Controller event scalars to lift into span attributes.
_CONTROLLER_EVENT_KEYS = (
    "trigger",
    "amplitude",
    "stick",
    "x",
    "y",
    "dx",
    "dy",
    "device_ts_ms",
    "causal_parent_ns",
)

# Phase 2 attribute namespace for re-entrant cascade markers.
_REENTRANT_ATTR = "qoresence.cascade.re_entrant"
_REENTRANT_CYCLE_LOBES_ATTR = "qoresence.cascade.cycle_lobes"
_REENTRANT_RISK_ATTR = "qoresence.cascade.risk"
_REENTRANT_WINDOW_ATTR = "qoresence.cascade.cycle_window_ns"
_HAS_REENTRANT_ATTR = "qoresence.cascade.has_re_entrant"
_CYCLE_COUNT_ATTR = "qoresence.cascade.cycle_count"

# OTel attribute values have length limits; keep sidecar lists small.
_MAX_ANOMALY_LOBES = 32


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_OTEL", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class _ReentrancyTracker:
    """Track per-thread lobe sequences to detect re-entrant fan-outs.

    The worker thread is the only writer. ``stats()`` is the cross-thread
    reader and must hold ``_lock``.
    """

    def __init__(
        self,
        window_ns: int,
        max_stack: int,
        anomaly_dir: Path | None = None,
    ) -> None:
        self._window_ns = int(window_ns)
        self._max_stack = int(max_stack)
        self._anomaly_dir = anomaly_dir
        self._stacks: dict[int, deque[tuple[str, int]]] = {}
        self._total = 0
        self._recent = 0
        self._recent_cycles: deque[dict[str, Any]] = deque(maxlen=64)
        self._lock = threading.Lock()
        self._anomaly_handle: Any = None

    def record(
        self, thread_id: int, lobe: str, clock_ns: int, session_id: str
    ) -> dict[str, Any] | None:
        """Record one lobe emit for a thread. Return a cycle dict if re-entrant."""
        with self._lock:
            stack = self._stacks.get(thread_id)
            if stack is None:
                stack = deque(maxlen=self._max_stack)
                self._stacks[thread_id] = stack

            # Evict entries older than the window (relative to the new clock).
            while stack and (clock_ns - stack[0][1]) > self._window_ns:
                stack.popleft()

            # Find the most recent prior occurrence of the same lobe that has
            # at least one different lobe between it and the new event. That
            # pattern is the definition of a re-entrant fan-out on this thread.
            cycle_start_idx: int | None = None
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == lobe:
                    # Is there a different lobe between i and the new position?
                    for j in range(i + 1, len(stack) + 1):
                        if j < len(stack):
                            if stack[j][0] != lobe:
                                cycle_start_idx = i
                                break
                        # j == len(stack) is the new event, same lobe, not different
                    if cycle_start_idx is not None:
                        break

            cycle: dict[str, Any] | None = None
            if cycle_start_idx is not None:
                cycle_lobes = [stack[k][0] for k in range(cycle_start_idx, len(stack))]
                cycle_lobes.append(lobe)
                cycle_window_ns = clock_ns - stack[cycle_start_idx][1]
                cycle = {
                    "session_id": str(session_id),
                    "thread_id": int(thread_id),
                    "lobe": str(lobe),
                    "clock_ns": int(clock_ns),
                    "cycle_lobes": cycle_lobes[:_MAX_ANOMALY_LOBES],
                    "cycle_window_ns": int(cycle_window_ns),
                }
                self._total += 1
                self._recent += 1
                self._recent_cycles.append(cycle)

            # Push the new event and trim.
            stack.append((lobe, clock_ns))
            return cycle

    def reset_recent(self) -> None:
        """Decay the recent-window counter (called by the periodic task)."""
        with self._lock:
            self._recent = 0

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "reentrant_cycles_total": int(self._total),
                "reentrant_cycles_recent": int(self._recent),
                "reentrant_lobe_counts": self._lobe_counts(),
                "recent_cycles": list(self._recent_cycles),
            }

    def _lobe_counts(self) -> dict[str, int]:
        """Tally which lobes appear most often as the re-entrant lobe."""
        counts: dict[str, int] = {}
        for cycle in self._recent_cycles:
            lobe = str(cycle.get("lobe", ""))
            if lobe:
                counts[lobe] = counts.get(lobe, 0) + 1
        return counts

    def write_anomaly(self, cycle: dict[str, Any], trace_id: str | None = None) -> None:
        """Best-effort JSONL anomaly log. Never blocks or raises to caller."""
        if self._anomaly_dir is None:
            return
        try:
            self._anomaly_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d")
            path = self._anomaly_dir / f"reentrant_{stamp}.jsonl"
            row = {
                "ts": time.time(),
                "trace_id": str(trace_id or ""),
                **{k: v for k, v in cycle.items() if k != "ts"},
            }
            if self._anomaly_handle is None:
                self._anomaly_handle = path.open("a", encoding="utf-8")
            self._anomaly_handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            self._anomaly_handle.flush()
        except Exception as e:
            log.debug("OTel re-entrancy anomaly write failed: %s", e)

    def close(self) -> None:
        with self._lock:
            try:
                if self._anomaly_handle is not None:
                    self._anomaly_handle.close()
                    self._anomaly_handle = None
            except Exception:
                pass


class OtelExporter:
    """Non-blocking OTLP exporter for bus cascades and capture metrics.

    Modeled on ``StreamrPublisher`` (opt-in, background worker, degrade
    gracefully) and ``LatencyStats`` (never raises into capture loops).
    If the ``otel`` extra is not installed, the exporter constructs as
    ``enabled=False`` and nothing else happens — no exception at import of
    ``qoresence`` or at construction.
    """

    def __init__(
        self,
        config: Any,
        bus: Any = None,
        session_identity: Any = None,
        tracer_provider: Any = None,
        meter_provider: Any = None,
    ) -> None:
        self.config = config
        self._dropped = 0
        self._exported = 0
        self._last_export_ns = 0
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(
            maxsize=int(getattr(config, "queue_size", 2048))
        )
        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None
        self._unsubscribe: Any = None
        self._tracer: Any = None
        self._meter: Any = None
        self._tracer_provider_owned: Any = None
        self._meter_provider_owned: Any = None
        self._instruments: dict[str, Any] = {}
        self._video_last: dict[str, float] = {}
        self._video_counters: dict[str, float] = {}
        self._latency_tick_ns = time.monotonic_ns()

        # Phase 2: re-entrancy tracker (worker-only writes, stats cross-thread).
        anomaly_dir = Path("logs/otel") if getattr(config, "enabled", False) else None
        self._reentrancy = _ReentrancyTracker(
            window_ns=int(getattr(config, "reentrancy_window_ns", 500_000_000)),
            max_stack=int(getattr(config, "reentrancy_max_stack", 16)),
            anomaly_dir=anomaly_dir,
        )

        # Phase 2: trace-ID ring for clip sidecars (worker writes, clip export reads).
        self._trace_ring: deque[tuple[str, int, int]] = deque(
            maxlen=int(getattr(config, "trace_ring_size", 128))
        )
        self._trace_ring_lock = threading.Lock()

        if not getattr(config, "enabled", False):
            return

        try:
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
        except Exception as e:  # extra not installed
            log.warning("OTel exporter disabled (missing 'otel' extra?): %s", e)
            return

        try:
            resource_attrs: dict[str, Any] = {
                "service.name": "qoresence",
                PLANE_ATTRIBUTE: PLANE,
            }
            session_id = getattr(session_identity, "session_id", None) or getattr(
                config, "session_id", ""
            )
            if session_id:
                resource_attrs["session.id"] = str(session_id)
            device_id = getattr(session_identity, "device_id_hex", None)
            if device_id:
                resource_attrs["device.id_hex"] = str(device_id)
            resource = Resource.create(resource_attrs)

            if tracer_provider is None:
                tp = TracerProvider(resource=resource)
                tp.add_span_processor(
                    BatchSpanProcessor(
                        OTLPSpanExporter(
                            endpoint=self.config.endpoint,
                            insecure=bool(getattr(config, "insecure", True)),
                        )
                    )
                )
                self._tracer_provider_owned = tp
                tracer_provider = tp
            if meter_provider is None:
                mp = MeterProvider(
                    resource=resource,
                    metric_readers=[
                        PeriodicExportingMetricReader(
                            OTLPMetricExporter(
                                endpoint=self.config.endpoint,
                                insecure=bool(getattr(config, "insecure", True)),
                            )
                        )
                    ],
                )
                self._meter_provider_owned = mp
                meter_provider = mp

            self._tracer = tracer_provider.get_tracer("qoresence.otel")
            self._meter = meter_provider.get_meter("qoresence.otel")
        except Exception as e:
            log.warning("OTel exporter setup failed, staying disabled: %s", e)
            self._tracer = None
            self._meter = None
            return

        # Enabled and wired. Start the worker BEFORE subscribing so the
        # queue always has a drainer.
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="qoresence-otel-exporter",
            daemon=True,
        )
        self._worker.start()

        if bus is not None:
            self._unsubscribe = bus.subscribe(self._on_event)

        log.info(
            "OTel exporter enabled: endpoint=%s plane=%s", config.endpoint, PLANE
        )

    @property
    def enabled(self) -> bool:
        return self._worker is not None

    # ── Hot path ─────────────────────────────────────────────────────────────

    def _on_event(self, event: BaseEvent) -> None:
        """Bus subscriber — runs synchronously on the emitting thread.

        MUST only enqueue. Strictly non-blocking, never raises, never emits,
        never takes a lock beyond the queue's own internal one.
        """
        try:
            if self._worker is None:
                return
            payload = getattr(event, "payload", None)
            rec: dict[str, Any] = {
                "session_id": getattr(event, "session_id", ""),
                "source_lobe": str(getattr(getattr(event, "source_lobe", ""), "value", "")),
                "event_type": str(getattr(getattr(event, "type", ""), "value", "")),
                "clock_ns": int(getattr(event, "clock_ns", 0) or 0),
                "thread_id": threading.get_ident(),
            }
            if isinstance(payload, dict):
                fs = payload.get("frame_seq")
                if isinstance(fs, (int, float)):
                    rec["frame_seq"] = int(fs)
                for k in _VIDEO_KEYS:
                    v = payload.get(k)
                    if isinstance(v, (int, float)):
                        rec[k] = float(v)
                for k in _COUPLING_KEYS:
                    v = payload.get(k)
                    if isinstance(v, (int, float, bool, str)):
                        rec[k] = v
                    elif isinstance(v, (list, tuple)) and len(v) <= 16:
                        # e.g. buttons, lag_band_ms
                        rec[k] = list(v)
                for k in _CONTROLLER_EVENT_KEYS:
                    v = payload.get(k)
                    if isinstance(v, (int, float, bool, str)):
                        rec[k] = v
            try:
                self._queue.put_nowait(rec)
            except queue.Full:
                # Drop-oldest so the emitter never waits.
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                self._dropped += 1
                try:
                    self._queue.put_nowait(rec)
                except queue.Full:
                    self._dropped += 1
        except Exception:
            # Never propagate into the bus fan-out.
            pass

    # ── Worker (off the hot path) ────────────────────────────────────────────

    def _worker_loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                rec = self._queue.get(timeout=0.1)
            except queue.Empty:
                self._periodic_tasks()
                continue
            batch: list[dict[str, Any]] = [rec]
            # Group a short cascade: up to cascade_max_events events with
            # clock_ns gaps under cascade_window_ns.
            max_events = int(getattr(self.config, "cascade_max_events", 64))
            window_ns = int(getattr(self.config, "cascade_window_ns", 250_000_000))
            last_ns = rec.get("clock_ns", 0)
            while len(batch) < max_events:
                try:
                    nxt = self._queue.get_nowait()
                except queue.Empty:
                    break
                gap = abs(nxt.get("clock_ns", 0) - last_ns)
                batch.append(nxt)
                last_ns = nxt.get("clock_ns", 0)
                if gap > window_ns:
                    break
            try:
                self._emit_cascade(batch)
            except Exception as e:
                log.debug("OTel cascade emit failed: %s", e)
            self._periodic_tasks()

    def _emit_cascade(self, batch: list[dict[str, Any]]) -> None:
        if not batch:
            return
        first_clock = int(batch[0].get("clock_ns", 0))
        last_clock = int(batch[-1].get("clock_ns", 0))
        session_id = str(batch[0].get("session_id", ""))

        if self._tracer is not None:
            with self._tracer.start_as_current_span("bus.cascade") as root:
                root.set_attribute(PLANE_ATTRIBUTE, PLANE)
                root.set_attribute("session.id", session_id)
                root.set_attribute("events", len(batch))
                root.set_attribute("clock_ns_first", first_clock)
                root.set_attribute("clock_ns_last", last_clock)

                # Capture the trace ID for clip sidecars.
                trace_id = self._trace_id_from_context()
                with self._trace_ring_lock:
                    self._trace_ring.append((trace_id, first_clock, last_clock))

                cycle_count = 0
                for rec in batch:
                    name = f"{rec.get('source_lobe', 'unknown')}.{rec.get('event_type', 'unknown')}"
                    with self._tracer.start_as_current_span(name) as span:
                        span.set_attribute(PLANE_ATTRIBUTE, PLANE)
                        span.set_attribute("session_id", str(rec.get("session_id", "")))
                        span.set_attribute("source_lobe", str(rec.get("source_lobe", "")))
                        span.set_attribute("event_type", str(rec.get("event_type", "")))
                        span.set_attribute("clock_ns", int(rec.get("clock_ns", 0)))
                        if "frame_seq" in rec:
                            span.set_attribute("frame_seq", int(rec["frame_seq"]))

                        # Coupling / controller telemetry on the span.
                        for k in _COUPLING_KEYS + _CONTROLLER_EVENT_KEYS:
                            if k in rec:
                                v = rec[k]
                                if isinstance(v, (int, float, bool, str)):
                                    span.set_attribute(k, v)
                                elif isinstance(v, (list, tuple)):
                                    span.set_attribute(k, list(v))

                        # Phase 2: causal re-entrancy detection.
                        cycle = self._reentrancy.record(
                            thread_id=int(rec.get("thread_id", 0)),
                            lobe=str(rec.get("source_lobe", "")),
                            clock_ns=int(rec.get("clock_ns", 0)),
                            session_id=str(rec.get("session_id", "")),
                        )
                        if cycle is not None:
                            cycle_count += 1
                            span.set_attribute(_REENTRANT_ATTR, True)
                            span.set_attribute(
                                _REENTRANT_CYCLE_LOBES_ATTR,
                                list(cycle.get("cycle_lobes", [])),
                            )
                            span.set_attribute(
                                _REENTRANT_RISK_ATTR, "same-thread re-entry"
                            )
                            span.set_attribute(
                                _REENTRANT_WINDOW_ATTR,
                                int(cycle.get("cycle_window_ns", 0)),
                            )
                            try:
                                self._reentrancy.write_anomaly(cycle, trace_id=trace_id)
                            except Exception:
                                pass
                            self._record_reentrant_metric(
                                str(cycle.get("lobe", "")),
                                str(rec.get("event_type", "")),
                            )

                if cycle_count:
                    root.set_attribute(_HAS_REENTRANT_ATTR, True)
                    root.set_attribute(_CYCLE_COUNT_ATTR, cycle_count)

        self._exported += len(batch)
        self._last_export_ns = time.monotonic_ns()
        self._update_metrics(batch)

    def _record_reentrant_metric(self, lobe: str, event_type: str) -> None:
        if self._meter is None:
            return
        try:
            ctr = self._instruments.get("reentrant_cycles")
            if ctr is None:
                ctr = self._meter.create_counter("qoresence_bus_reentrant_cycles_total")
                self._instruments["reentrant_cycles"] = ctr
            ctr.add(1, attributes={"lobe": lobe, "event_type": event_type})
        except Exception as e:
            log.debug("OTel re-entrant metric failed: %s", e)

    def _update_metrics(self, batch: list[dict[str, Any]]) -> None:
        if self._meter is None:
            return
        try:
            ctr = self._instruments.get("bus_events")
            if ctr is None:
                ctr = self._meter.create_counter("qoresence_bus_events_total")
                self._instruments["bus_events"] = ctr
            for rec in batch:
                ctr.add(
                    1,
                    attributes={
                        "lobe": str(rec.get("source_lobe", "")),
                        "event_type": str(rec.get("event_type", "")),
                    },
                )
            for rec in batch:
                for k in _VIDEO_KEYS:
                    if k in rec:
                        self._video_last[k] = float(rec[k])

            # Coupling / controller telemetry gauges from coupling_score events.
            for rec in batch:
                if rec.get("event_type") == "coupling_score" and self._meter is not None:
                    self._update_coupling_gauges(rec)

            for k in ("age_s", "fps"):
                if k in self._video_last:
                    g = self._instruments.get(f"video_{k}")
                    if g is None:
                        g = self._meter.create_gauge(f"qoresence_video_{k}")
                        self._instruments[f"video_{k}"] = g
                    g.set(self._video_last[k])
            # frames / pushes: monotone counters — export the delta.
            for k in ("frames", "pushes"):
                v = self._video_last.get(k)
                if v is None:
                    continue
                prev = self._video_counters.get(k)
                c = self._instruments.get(f"video_{k}_total")
                if c is None:
                    c = self._meter.create_counter(f"qoresence_video_{k}_total")
                    self._instruments[f"video_{k}_total"] = c
                if prev is not None and v > prev:
                    c.add(v - prev)
                self._video_counters[k] = v
        except Exception as e:
            log.debug("OTel metric update failed: %s", e)

    def _update_coupling_gauges(self, rec: dict[str, Any]) -> None:
        """Export controller/coupling scalars as gauges."""
        if self._meter is None:
            return
        try:
            phrase = str(rec.get("phrase", "IDLE"))
            attrs = {"phrase": phrase}

            _GAUGE_KEYS = {
                "coupling": "qoresence_coupling",
                "coupling_ema": "qoresence_coupling_ema",
                "input_energy": "qoresence_input_energy",
                "edge_energy": "qoresence_edge_energy",
                "hold_energy": "qoresence_hold_energy",
                "phrase_conf": "qoresence_phrase_conf",
                "stick_gyro_r": "qoresence_stick_gyro_r",
                "stick_motion_r": "qoresence_stick_motion_r",
                "video_age_s": "qoresence_video_age_s",
            }
            for key, metric_name in _GAUGE_KEYS.items():
                v = rec.get(key)
                if isinstance(v, (int, float)):
                    g = self._instruments.get(metric_name)
                    if g is None:
                        g = self._meter.create_gauge(metric_name)
                        self._instruments[metric_name] = g
                    g.set(float(v), attributes=attrs)

            # imu_bodied as a 0/1 gauge.
            imu = rec.get("imu_bodied")
            if isinstance(imu, bool):
                g = self._instruments.get("qoresence_imu_bodied")
                if g is None:
                    g = self._meter.create_gauge("qoresence_imu_bodied")
                    self._instruments["qoresence_imu_bodied"] = g
                g.set(1.0 if imu else 0.0, attributes=attrs)

            # input_events as a counter (monotonically increasing total).
            n = rec.get("input_events")
            if isinstance(n, (int, float)):
                c = self._instruments.get("qoresence_controller_input_events_total")
                if c is None:
                    c = self._meter.create_counter("qoresence_controller_input_events_total")
                    self._instruments["qoresence_controller_input_events_total"] = c
                c.add(float(n), attributes=attrs)
        except Exception as e:
            log.debug("OTel coupling gauge update failed: %s", e)

    def _periodic_tasks(self) -> None:
        now = time.monotonic_ns()
        if now - self._latency_tick_ns < 5_000_000_000:
            return
        self._latency_tick_ns = now

        # Phase 2: decay the recent re-entrancy window for health/pilot auditor.
        self._reentrancy.reset_recent()

        if self._dropped and self._meter is not None:
            try:
                c = self._instruments.get("dropped")
                if c is None:
                    c = self._meter.create_counter("qoresence_otel_dropped")
                    self._instruments["dropped"] = c
                c.add(self._dropped)
                self._dropped = 0
            except Exception:
                pass
        try:
            from qoresence.observability import get_latency_stats

            summary = get_latency_stats().summary()
            names = summary.get("names") or {}
            if self._meter is not None:
                g95 = self._instruments.get("latency_p95")
                if g95 is None:
                    g95 = self._meter.create_gauge("qoresence_latency_p95_ms")
                    self._instruments["latency_p95"] = g95
                for name, vals in names.items():
                    if isinstance(vals, dict) and "p95_ms" in vals:
                        g95.set(
                            float(vals["p95_ms"]),
                            attributes={"name": str(name)},
                        )
        except Exception:
            pass

    # ── Public API ───────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Snapshot for the Deck ``/health`` payload and pilot auditor."""
        out = {
            "enabled": self.enabled,
            "exported": int(self._exported),
            "dropped": int(self._dropped),
            "last_export_ns": int(self._last_export_ns),
        }
        out.update(self._reentrancy.stats())
        return out

    def trace_ids_for_window(self, start_ns: int, end_ns: int) -> list[str]:
        """Return trace IDs whose cascade window overlaps [start_ns, end_ns].

        Called from ``HdmiClipBuffer.export`` (clip sidecars). Cross-thread
        safe: worker appends, this method reads with a lock.
        """
        with self._trace_ring_lock:
            ring = list(self._trace_ring)
        trace_ids: list[str] = []
        for trace_id, first, last in ring:
            if last < start_ns or first > end_ns:
                continue
            if trace_id and trace_id not in trace_ids:
                trace_ids.append(trace_id)
        return trace_ids

    def stop(self) -> None:
        """Unsubscribe, stop the worker, flush with a short timeout."""
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            except Exception:
                pass
            self._unsubscribe = None
        self._stop_evt.set()
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=2.0)
        self._worker = None
        self._reentrancy.close()
        for provider in (self._tracer_provider_owned, self._meter_provider_owned):
            if provider is None:
                continue
            try:
                provider.force_flush(timeout_millis=2000)
                provider.shutdown()
            except Exception:
                pass
        self._tracer_provider_owned = None
        self._meter_provider_owned = None

    def _trace_id_from_context(self) -> str:
        """Return the current span's trace ID as a 32-hex string, or empty."""
        try:
            from opentelemetry import trace

            ctx = trace.get_current_span().get_span_context()
            if ctx is None or not ctx.trace_id:
                return ""
            return format(ctx.trace_id, "032x")
        except Exception:
            return ""


def get_otel_exporter() -> OtelExporter | None:
    """Return the process-wide exporter, if one was started (for /health)."""
    return _get_or_set_exporter()


_singleton: OtelExporter | None = None
_singleton_lock = threading.Lock()


def _get_or_set_exporter(exporter: OtelExporter | None = None) -> OtelExporter | None:
    global _singleton
    with _singleton_lock:
        if exporter is not None:
            _singleton = exporter
        return _singleton


def make_otel_exporter_from_config(
    config: Any, bus: Any = None, session_identity: Any = None
) -> OtelExporter | None:
    """Factory used by cli.py — returns None unless enabled (Streamr pattern).

    Honors ``QORESENCE_OTEL=1`` as an env override, mirroring A2A gating.
    """
    enabled = bool(getattr(config, "enabled", False)) or _env_enabled()
    if not enabled:
        return None
    exporter = OtelExporter(config, bus=bus, session_identity=session_identity)
    if not exporter.enabled:
        return None
    _get_or_set_exporter(exporter)
    return exporter
