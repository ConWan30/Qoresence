"""
Prometheus Metrics Exporter for trio-retina

Provides /metrics endpoint for trio-retina validation statistics.
Integrates with RetinaEventBus.get_trio_stats() and TrioRetinaValidator.stats().
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import TrioRetinaConfig
    from .validator import TrioRetinaValidator

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    Counter = Gauge = Histogram = Info = CollectorRegistry = object


# Custom registry for trio-retina metrics (avoids global registry conflicts in tests)
_trio_registry: CollectorRegistry | None = None


def get_trio_registry() -> CollectorRegistry:
    """Get or create trio-retina specific registry."""
    global _trio_registry
    if not PROMETHEUS_AVAILABLE:
        return None
    if _trio_registry is None:
        _trio_registry = CollectorRegistry()
    return _trio_registry


def reset_trio_registry():
    """Reset registry (for testing)."""
    global _trio_registry
    _trio_registry = None


@dataclass
class TrioRetinaMetrics:
    """Prometheus metrics for trio-retina validation layer."""

    # Validation counters
    validations_total: Counter = field(
        default_factory=lambda: Counter(
            "qoresence_trio_retina_validations_total",
            "Total number of trio-retina validations performed",
            ["result"],  # "success", "failure"
            registry=get_trio_registry(),
        )
    )

    # Validation latency
    validation_duration_seconds: Histogram = field(
        default_factory=lambda: Histogram(
            "qoresence_trio_retina_validation_duration_seconds",
            "Time spent in trio-retina WASM validation",
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=get_trio_registry(),
        )
    )

    # Payload size
    payload_size_bytes: Histogram = field(
        default_factory=lambda: Histogram(
            "qoresence_trio_retina_payload_size_bytes",
            "Size of EvmLogPayload submitted for validation",
            buckets=[100, 500, 1000, 2000, 5000, 10000, 20000, 50000],
            registry=get_trio_registry(),
        )
    )

    # Flush interval tracking
    flush_interval_seconds: Gauge = field(
        default_factory=lambda: Gauge(
            "qoresence_trio_retina_flush_interval_seconds",
            "Configured flush interval for batch validation",
            registry=get_trio_registry(),
        )
    )

    # Last flush timestamp
    last_flush_timestamp: Gauge = field(
        default_factory=lambda: Gauge(
            "qoresence_trio_retina_last_flush_timestamp",
            "Unix timestamp of last validation flush",
            registry=get_trio_registry(),
        )
    )

    # Pending events in buffer
    pending_events: Gauge = field(
        default_factory=lambda: Gauge(
            "qoresence_trio_retina_pending_events",
            "Number of events waiting in validation buffer",
            registry=get_trio_registry(),
        )
    )

    # WASM runner status
    wasm_runner_status: Gauge = field(
        default_factory=lambda: Gauge(
            "qoresence_trio_retina_wasm_runner_status",
            "WASM runner status (1=healthy, 0=error, -1=not initialized)",
            registry=get_trio_registry(),
        )
    )

    # PQ commitment source
    pq_commitment_source: Info = field(
        default_factory=lambda: Info(
            "qoresence_trio_retina_pq_commitment_source",
            "PQ commitment generation mode",
            registry=get_trio_registry(),
        )
    )

    # Trio-retina enabled state
    enabled: Gauge = field(
        default_factory=lambda: Gauge(
            "qoresence_trio_retina_enabled",
            "Whether trio-retina validation is enabled (1) or disabled (0)",
            registry=get_trio_registry(),
        )
    )

    # Node/Session verification flags
    node_session_verify: Gauge = field(
        default_factory=lambda: Gauge(
            "qoresence_trio_retina_node_session_verify",
            "Whether node/session verification is enabled (1) or disabled (0)",
            registry=get_trio_registry(),
        )
    )

    events_root_verify: Gauge = field(
        default_factory=lambda: Gauge(
            "qoresence_trio_retina_events_root_verify",
            "Whether events root verification is enabled (1) or disabled (0)",
            registry=get_trio_registry(),
        )
    )

    def __post_init__(self):
        if not PROMETHEUS_AVAILABLE:
            return

    def record_validation(self, success: bool, duration_ms: float, payload_size: int):
        """Record a validation result."""
        if not PROMETHEUS_AVAILABLE:
            return
        result = "success" if success else "failure"
        self.validations_total.labels(result=result).inc()
        self.validation_duration_seconds.observe(duration_ms / 1000.0)
        self.payload_size_bytes.observe(payload_size)

    def update_flush_state(self, interval_s: float, last_flush_ns: int, pending: int):
        """Update flush-related metrics."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.flush_interval_seconds.set(interval_s)
        self.last_flush_timestamp.set(last_flush_ns / 1e9)
        self.pending_events.set(pending)

    def update_wasm_status(self, healthy: bool, initialized: bool = True):
        """Update WASM runner health."""
        if not PROMETHEUS_AVAILABLE:
            return
        if not initialized:
            self.wasm_runner_status.set(-1)
        elif healthy:
            self.wasm_runner_status.set(1)
        else:
            self.wasm_runner_status.set(0)

    def update_config(self, enabled: bool, pq_source: str, node_session: bool, events_root: bool):
        """Update configuration metrics."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.enabled.set(1 if enabled else 0)
        self.pq_commitment_source.info({"source": pq_source})
        self.node_session_verify.set(1 if node_session else 0)
        self.events_root_verify.set(1 if events_root else 0)


# Global metrics instance
_trio_metrics: TrioRetinaMetrics | None = None


def get_trio_metrics() -> TrioRetinaMetrics:
    """Get or create global trio-retina metrics instance."""
    global _trio_metrics
    if _trio_metrics is None:
        _trio_metrics = TrioRetinaMetrics()
    return _trio_metrics


def reset_trio_metrics():
    """Reset global metrics (for testing)."""
    global _trio_metrics
    _trio_metrics = None
    reset_trio_registry()


# ──────────────────────────────────────────────────────────────────────
# Integration with TrioRetinaValidator
# ──────────────────────────────────────────────────────────────────────


def instrument_validator(validator: TrioRetinaValidator) -> None:
    """
    Instrument a TrioRetinaValidator with Prometheus metrics.

    Call this after creating the validator to enable metrics collection.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    metrics = get_trio_metrics()
    config = validator.config

    # Update config metrics
    metrics.update_config(
        enabled=config.enabled,
        pq_source=config.pq_commitment_source,
        node_session=config.node_session_verify,
        events_root=config.retina_events_root_verify,
    )

    # Update flush interval
    metrics.update_flush_state(
        interval_s=config.flush_interval_s,
        last_flush_ns=0,
        pending=0,
    )

    # Wrap validate_batch to record metrics
    original_validate = validator.validate_batch

    async def instrumented_validate(events):
        start = time.perf_counter()
        try:
            result = await original_validate(events)
            duration_ms = (time.perf_counter() - start) * 1000

            # Estimate payload size
            payload_size = sum(len(str(e)) for e in events) * 2  # rough estimate

            metrics.record_validation(
                success=result.ok,
                duration_ms=duration_ms,
                payload_size=payload_size,
            )

            # Update flush state from validator stats
            stats = validator.get_stats()
            metrics.update_flush_state(
                interval_s=config.flush_interval_s,
                last_flush_ns=stats.get("last_flush_ns", 0),
                pending=stats.get("pending_events", 0),
            )

            return result
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            metrics.record_validation(
                success=False,
                duration_ms=duration_ms,
                payload_size=0,
            )
            raise

    validator.validate_batch = instrumented_validate  # type: ignore


# ──────────────────────────────────────────────────────────────────────
# HTTP /metrics endpoint (for aiohttp/FastAPI/Starlette)
# ──────────────────────────────────────────────────────────────────────


def create_metrics_endpoint():
    """
    Create a Prometheus /metrics endpoint handler.

    Returns a callable compatible with aiohttp, FastAPI, Starlette, etc.
    """
    if not PROMETHEUS_AVAILABLE:

        async def not_available(request):
            from aiohttp import web

            return web.Response(text="prometheus_client not installed", status=503)

        return not_available

    async def metrics_handler(request):
        from aiohttp import web

        # Update metrics from event bus if available
        # This would be called periodically or on each request
        output = generate_latest()
        return web.Response(body=output, content_type=CONTENT_TYPE_LATEST)

    return metrics_handler


# ──────────────────────────────────────────────────────────────────────
# Middleware for automatic instrumentation
# ──────────────────────────────────────────────────────────────────────


class TrioRetinaMetricsMiddleware:
    """
    ASGI middleware to expose /metrics endpoint.

    Usage:
        app.add_middleware(TrioRetinaMetricsMiddleware, path="/metrics")
    """

    def __init__(self, app, path: str = "/metrics"):
        self.app = app
        self.path = path
        self._handler = create_metrics_endpoint()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == self.path:
            await self._handler(scope, receive, send)
        else:
            await self.app(scope, receive, send)


# ──────────────────────────────────────────────────────────────────────
# Convenience function for manual metric updates
# ──────────────────────────────────────────────────────────────────────


def update_trio_metrics_from_stats(stats: dict, config: TrioRetinaConfig) -> None:
    """
    Update Prometheus metrics from validator stats dict.

    Call this periodically (e.g., from a background task).
    """
    if not PROMETHEUS_AVAILABLE:
        return

    metrics = get_trio_metrics()

    metrics.update_config(
        enabled=config.enabled,
        pq_source=config.pq_commitment_source,
        node_session=config.node_session_verify,
        events_root=config.retina_events_root_verify,
    )

    metrics.update_flush_state(
        interval_s=config.flush_interval_s,
        last_flush_ns=stats.get("last_flush_ns", 0),
        pending=stats.get("pending_events", 0),
    )

    metrics.update_wasm_status(
        healthy=stats.get("wasm_healthy", False),
        initialized=stats.get("wasm_initialized", False),
    )
