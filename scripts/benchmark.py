#!/usr/bin/env python3
"""
Qoresence × trio-retina Performance Benchmarks

Measures:
- Event bus throughput (events/sec)
- WASM validation latency (p50, p95, p99)
- Payload building overhead
- Memory usage under load
"""

from __future__ import annotations

import asyncio
import gc
import json
import os
import statistics
import sys
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Ensure local qoresence is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from qoresence.core import RetinaEventBus, SessionAuthority, SourceLobe, EventType, clock_ns
from qoresence.trio import (
    TrioRetinaConfig,
    EvmLogPayload,
    build_evm_log_payload,
    WasmtimeRunner,
    WasmResult,
)


@dataclass
class BenchmarkResult:
    name: str
    iterations: int
    total_time_s: float
    ops_per_sec: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_max_ms: float
    memory_peak_mb: float


class BenchmarkRunner:
    def __init__(self):
        self.results: List[BenchmarkResult] = []

    def run(self, name: str, iterations: int, func, *args, **kwargs) -> BenchmarkResult:
        """Run a benchmark and collect statistics."""
        latencies = []
        tracemalloc.start()
        
        start = time.perf_counter()
        for _ in range(iterations):
            iter_start = time.perf_counter()
            func(*args, **kwargs)
            latencies.append((time.perf_counter() - iter_start) * 1000)
        total_time = time.perf_counter() - start
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        latencies.sort()
        result = BenchmarkResult(
            name=name,
            iterations=iterations,
            total_time_s=total_time,
            ops_per_sec=iterations / total_time,
            latency_p50_ms=latencies[len(latencies) // 2],
            latency_p95_ms=latencies[int(len(latencies) * 0.95)],
            latency_p99_ms=latencies[int(len(latencies) * 0.99)],
            latency_max_ms=latencies[-1],
            memory_peak_mb=peak / 1024 / 1024,
        )
        self.results.append(result)
        return result

    def run_async(self, name: str, iterations: int, func, *args, **kwargs) -> BenchmarkResult:
        """Run an async benchmark."""
        latencies = []
        tracemalloc.start()
        
        async def run_all():
            for _ in range(iterations):
                iter_start = time.perf_counter()
                await func(*args, **kwargs)
                latencies.append((time.perf_counter() - iter_start) * 1000)
        
        start = time.perf_counter()
        asyncio.run(run_all())
        total_time = time.perf_counter() - start
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        latencies.sort()
        result = BenchmarkResult(
            name=name,
            iterations=iterations,
            total_time_s=total_time,
            ops_per_sec=iterations / total_time,
            latency_p50_ms=latencies[len(latencies) // 2],
            latency_p95_ms=latencies[int(len(latencies) * 0.95)],
            latency_p99_ms=latencies[int(len(latencies) * 0.99)],
            latency_max_ms=latencies[-1],
            memory_peak_mb=peak / 1024 / 1024,
        )
        self.results.append(result)
        return result

    def print_results(self):
        """Print formatted results."""
        print("\n" + "=" * 100)
        print("BENCHMARK RESULTS")
        print("=" * 100)
        print(f"{'Test':<35} {'Iters':>8} {'Ops/s':>12} {'p50(ms)':>10} {'p95(ms)':>10} {'p99(ms)':>10} {'Max(ms)':>10} {'Peak(MB)':>10}")
        print("-" * 100)
        for r in self.results:
            print(f"{r.name:<35} {r.iterations:>8} {r.ops_per_sec:>12.1f} {r.latency_p50_ms:>10.2f} {r.latency_p95_ms:>10.2f} {r.latency_p99_ms:>10.2f} {r.latency_max_ms:>10.2f} {r.memory_peak_mb:>10.1f}")
        print("=" * 100)

    def save_json(self, path: str):
        """Save results to JSON."""
        data = [{
            "name": r.name,
            "iterations": r.iterations,
            "total_time_s": r.total_time_s,
            "ops_per_sec": r.ops_per_sec,
            "latency_p50_ms": r.latency_p50_ms,
            "latency_p95_ms": r.latency_p95_ms,
            "latency_p99_ms": r.latency_p99_ms,
            "latency_max_ms": r.latency_max_ms,
            "memory_peak_mb": r.memory_peak_mb,
        } for r in self.results]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


def benchmark_event_bus_emit():
    """Benchmark event bus emission throughput."""
    bus = RetinaEventBus(session_id="bench_session", enable_ws=False)
    event = SessionAuthority.mint(session_id="bench_session")
    
    def emit_event():
        bus.emit_raw(
            source_lobe=SourceLobe.STREAMER,
            event_type="frame_stats",
            payload={"frame_id": 1, "timestamp_ns": clock_ns()},
            clock_ns_override=clock_ns(),
            session_head_ns=event.session_head_ns,
        )
    
    return emit_event


def benchmark_payload_build():
    """Benchmark EvmLogPayload building."""
    session = SessionAuthority.mint(
        session_id="bench_session",
        device_id_hex="a" * 64,
    )
    events = [{"event_id": f"evt_{i}", "type": "test", "data": {"x": i}} for i in range(100)]
    config = TrioRetinaConfig(enabled=True)
    
    def build_payload():
        build_evm_log_payload(
            session=session,
            events=events,
            config=config,
            first_session_id="first_session",
        )
    
    return build_payload


def benchmark_payload_json():
    """Benchmark payload JSON serialization."""
    payload = EvmLogPayload(
        device_id="a" * 64,
        block_number=12345,
        payload_hash="b" * 64,
        signature="c" * 64,
        pq_commitment="d" * 64,
        retina_state_commitment="e" * 64,
        events_root="f" * 64,
        node_id="g" * 64,
    )
    
    def serialize():
        payload.to_json()
    
    def deserialize():
        EvmLogPayload.from_json(payload.to_json())
    
    return serialize, deserialize


async def benchmark_wasm_validation_mock():
    """Benchmark WASM validation with mocked runner."""
    config = TrioRetinaConfig(enabled=True, wasm_path="test.wasm")
    runner = WasmtimeRunner(config)
    
    payload = EvmLogPayload(
        device_id="a" * 64,
        block_number=12345,
        payload_hash="b" * 64,
        signature="c" * 64,
        pq_commitment="d" * 64,
    )
    
    # Mock the actual WASM call
    original_run = runner.run
    
    async def mock_run(p):
        return WasmResult(
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=1.0,
            payload=p,
        )
    
    runner.run = mock_run
    
    async def validate():
        await runner.run(payload)
    
    return validate


async def benchmark_wasm_validation_real():
    """Benchmark real WASM validation (requires wasmtime and WASM file)."""
    wasm_path = Path("w3bstream_applet.wasm")
    if not wasm_path.exists():
        wasm_path = Path("../vapi-pebble-prototype/w3bstream/applet/target/wasm32-unknown-unknown/release/w3bstream_applet.wasm")
    
    if not wasm_path.exists():
        print("WASM file not found, skipping real WASM benchmark")
        return None
    
    config = TrioRetinaConfig(enabled=True, wasm_path=str(wasm_path))
    runner = WasmtimeRunner(config)
    
    payload = EvmLogPayload(
        device_id="a" * 64,
        block_number=12345,
        payload_hash="b" * 64,
        signature="c" * 64,
        pq_commitment="d" * 64,
    )
    
    async def validate():
        return await runner.run(payload)
    
    return validate


def benchmark_block_number_fetch():
    """Benchmark block number fetching (mocked)."""
    config = TrioRetinaConfig(enabled=True)
    
    # Mock the async call
    original_get = config.get_block_number
    
    async def mock_get():
        return 12345
    
    config.get_block_number = mock_get
    
    async def fetch():
        return await config.get_block_number()
    
    return fetch


def benchmark_pq_commitment_mock():
    """Benchmark mock PQ commitment generation."""
    from qoresence.trio.payload import mock_pq_commitment
    
    def gen():
        return mock_pq_commitment()
    
    return gen


def benchmark_node_id_compute():
    """Benchmark node_id computation."""
    from qoresence.trio.payload import compute_node_id
    
    def compute():
        return compute_node_id("a" * 64, "session_123")
    
    return compute


def benchmark_events_root():
    """Benchmark events root computation."""
    from qoresence.trio.payload import compute_events_root
    
    event_ids = [f"evt_{i}" for i in range(1000)]
    
    def compute():
        return compute_events_root(event_ids)
    
    return compute


def run_benchmarks():
    """Run all benchmarks."""
    runner = BenchmarkRunner()
    
    print("Running Qoresence × trio-retina Performance Benchmarks")
    print("=" * 60)
    
    # Event bus benchmarks
    print("\n1. Event Bus Throughput...")
    emit_fn = benchmark_event_bus_emit()
    runner.run("EventBus.emit_raw (100 events)", 10000, emit_fn)
    
    # Payload building
    print("2. Payload Building...")
    build_fn = benchmark_payload_build()
    runner.run("build_evm_log_payload (100 events)", 1000, build_fn)
    
    # JSON serialization
    print("3. Payload JSON Serialization...")
    serialize_fn, deserialize_fn = benchmark_payload_json()
    runner.run("EvmLogPayload.to_json()", 10000, serialize_fn)
    runner.run("EvmLogPayload.from_json()", 10000, deserialize_fn)
    
    # WASM validation (mocked)
    print("4. WASM Validation (mocked)...")
    validate_mock_fn = asyncio.run(benchmark_wasm_validation_mock())
    runner.run_async("WasmtimeRunner.run() [mocked]", 1000, validate_mock_fn)
    
    # Real WASM validation (if available)
    print("5. WASM Validation (real)...")
    validate_real_fn = asyncio.run(benchmark_wasm_validation_real())
    if validate_real_fn:
        runner.run_async("WasmtimeRunner.run() [real]", 100, validate_real_fn)
    
    # Block number fetch
    print("6. Block Number Fetch...")
    fetch_fn = benchmark_block_number_fetch()
    runner.run_async("config.get_block_number() [mocked]", 1000, fetch_fn)
    
    # PQ commitment
    print("7. PQ Commitment...")
    pq_fn = benchmark_pq_commitment_mock()
    runner.run("mock_pq_commitment()", 10000, pq_fn)
    
    # Node ID computation
    print("8. Node ID Computation...")
    node_id_fn = benchmark_node_id_compute()
    runner.run("compute_node_id()", 10000, node_id_fn)
    
    # Events root
    print("9. Events Root Computation...")
    events_root_fn = benchmark_events_root()
    runner.run("compute_events_root(1000 events)", 1000, events_root_fn)
    
    # Memory pressure test
    print("10. Memory Pressure Test...")
    def memory_test():
        # Create many payloads
        payloads = []
        for i in range(100):
            session = SessionAuthority.mint(session_id=f"bench_{i}")
            events = [{"event_id": f"evt_{j}", "type": "test"} for j in range(10)]
            config = TrioRetinaConfig(enabled=True)
            p = build_evm_log_payload(session, events, config, f"first_{i}")
            payloads.append(p.to_json())
        return len(payloads)
    
    runner.run("Memory: 100 payloads * 10 events", 100, memory_test)
    
    # Print results
    runner.print_results()
    
    # Save to JSON
    runner.save_json("benchmark_results.json")
    print("\nResults saved to benchmark_results.json")
    
    return runner


if __name__ == "__main__":
    # Warm up
    print("Warming up...")
    for _ in range(100):
        benchmark_event_bus_emit()()
        benchmark_payload_build()()
    
    gc.collect()
    
    # Run benchmarks
    run_benchmarks()