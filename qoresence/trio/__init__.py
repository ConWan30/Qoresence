"""
Qoresence × trio-retina Integration Module

Provides mechanical validation of Qoresence session events via the
MachineFi trio-retina w3bstream applet (WASM).
"""

from __future__ import annotations

from .config import TrioRetinaConfig
from .metrics import (
    TrioRetinaMetrics,
    TrioRetinaMetricsMiddleware,
    create_metrics_endpoint,
    get_trio_metrics,
    get_trio_registry,
    instrument_validator,
    reset_trio_metrics,
    reset_trio_registry,
    update_trio_metrics_from_stats,
)
from .payload import (
    EvmLogPayload,
    build_evm_log_payload,
    compute_events_root,
    compute_node_id,
    compute_payload_hash,
    mock_pq_commitment,
    mock_signature,
    try_real_pq_commitment,
)
from .validator import TrioRetinaValidator, ValidationResult, create_validator
from .wasm import WasmResult, WasmtimeRunner, create_runner

__all__ = [
    "TrioRetinaConfig",
    "EvmLogPayload",
    "build_evm_log_payload",
    "compute_node_id",
    "compute_payload_hash",
    "compute_events_root",
    "mock_pq_commitment",
    "mock_signature",
    "try_real_pq_commitment",
    "WasmtimeRunner",
    "WasmResult",
    "TrioRetinaValidator",
    "ValidationResult",
    "create_validator",
    "create_runner",
    # Metrics
    "TrioRetinaMetrics",
    "get_trio_metrics",
    "instrument_validator",
    "create_metrics_endpoint",
    "TrioRetinaMetricsMiddleware",
    "update_trio_metrics_from_stats",
    "reset_trio_metrics",
    "get_trio_registry",
    "reset_trio_registry",
]
