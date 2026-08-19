"""Opt-in OpenTelemetry exporter for Qoresence (observation plane only).

Exports bus-cascade traces and capture-health metrics over OTLP gRPC to a
local Collector (default ``http://127.0.0.1:4317``). Enable with ``--otel``
or ``QORESENCE_OTEL=1``. Default OFF.

HARD RULES (same class as the AGENTS.md event-bus locking rules):

1. ``_on_event`` runs synchronously on the emitting thread — it must ONLY
   enqueue (bounded queue, drop-oldest). Never block, never emit bus events,
   never acquire a lobe lock.
2. No payload dumps. Only small scalar attributes (session_id, source_lobe,
   event_type, clock_ns, frame_seq, capture-health scalars).
3. No session-long mega-trace. Traces are short cascades: a bounded group of
   events within one ``clock_ns`` window becomes one small trace tree.
4. Every resource and span carries ``plane=qoresence-observation``.

See docs/OTEL.md.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Any

from qoresence.core import BaseEvent

log = logging.getLogger(__name__)

PLANE_ATTRIBUTE = "plane"
PLANE = "qoresence-observation"

# Small scalar keys lifted from event payloads into the queue record (and
# from there into gauges). Anything else in the payload is ignored.
_VIDEO_KEYS = ("age_s", "frames", "pushes", "fps")


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_OTEL", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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
        self._latency_tick_ns = 0

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
            }
            if isinstance(payload, dict):
                fs = payload.get("frame_seq")
                if isinstance(fs, (int, float)):
                    rec["frame_seq"] = int(fs)
                for k in _VIDEO_KEYS:
                    v = payload.get(k)
                    if isinstance(v, (int, float)):
                        rec[k] = float(v)
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
        if self._tracer is not None:
            with self._tracer.start_as_current_span("bus.cascade") as root:
                root.set_attribute(PLANE_ATTRIBUTE, PLANE)
                root.set_attribute("session.id", str(batch[0].get("session_id", "")))
                root.set_attribute("events", len(batch))
                root.set_attribute("clock_ns_first", int(batch[0].get("clock_ns", 0)))
                root.set_attribute("clock_ns_last", int(batch[-1].get("clock_ns", 0)))
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
        self._exported += len(batch)
        self._last_export_ns = time.monotonic_ns()
        self._update_metrics(batch)

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

    def _periodic_tasks(self) -> None:
        now = time.monotonic_ns()
        if now - self._latency_tick_ns < 5_000_000_000:
            return
        self._latency_tick_ns = now
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
        """Snapshot for the Deck ``/health`` payload."""
        return {
            "enabled": self.enabled,
            "exported": int(self._exported),
            "dropped": int(self._dropped),
            "last_export_ns": int(self._last_export_ns),
        }

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
