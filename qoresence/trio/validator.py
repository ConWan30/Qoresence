"""
TrioRetina Validator — Orchestrates Qoresence → trio-retina Validation

Integrates with RetinaEventBus and PresenceFusionEngine to provide
optional mechanical validation via w3bstream applet.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from qoresence.core import RetinaEventBus, SessionIdentity, SourceLobe

from .config import TrioRetinaConfig
from .payload import EvmLogPayload, build_evm_log_payload, get_posp_root, get_visual_oracle_root
from .wasm import WasmResult, create_runner

log = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation cycle."""

    ok: bool
    exit_code: int
    error_description: str
    duration_ms: float
    payload: EvmLogPayload | None = None
    events_validated: int = 0
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


class EventBuffer:
    """Thread-safe event buffer for batch validation."""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._buffer: deque[dict] = deque(maxlen=max_size)
        self._lock = asyncio.Lock()

    async def add(self, event: dict) -> None:
        async with self._lock:
            self._buffer.append(event)

    async def add_batch(self, events: list[dict]) -> None:
        async with self._lock:
            self._buffer.extend(events)

    async def drain(self) -> list[dict]:
        async with self._lock:
            events = list(self._buffer)
            self._buffer.clear()
            return events

    async def size(self) -> int:
        async with self._lock:
            return len(self._buffer)

    async def is_full(self) -> bool:
        async with self._lock:
            return len(self._buffer) >= self.max_size


class TrioRetinaValidator:
    """
    Main validator orchestrating Qoresence → trio-retina validation.

    Integrates with:
    - RetinaEventBus: subscribes to events, batches for validation
    - PresenceFusionEngine: validates presence reports
    - VisualRuntime: provides visual oracle state root
    - OutcomeRuntime: provides PoSP session root

    Two validation modes:
    1. validate_on_ingest: validate each event immediately (strict, higher latency)
    2. validate_on_flush: batch events, validate periodically (default)
    """

    def __init__(
        self,
        config: TrioRetinaConfig,
        session: SessionIdentity,
        event_bus: RetinaEventBus | None = None,
        visual_oracle_root_provider: Callable[[], str] | None = None,
        posp_root_provider: Callable[[], str] | None = None,
        first_session_id: str | None = None,
        device_key: bytes | None = None,
    ):
        self.config = config
        self.session = session
        self.event_bus = event_bus
        self.visual_oracle_root_provider = visual_oracle_root_provider or get_visual_oracle_root
        self.posp_root_provider = posp_root_provider or get_posp_root
        self.first_session_id = first_session_id
        self.device_key = device_key

        # Runner
        self.runner = create_runner(config)

        # State
        self._running = False
        self._buffer = EventBuffer(config.max_batch_size)
        self._flush_task: asyncio.Task | None = None
        self._ingest_subscription_id: Callable[[], None] | None = None

        # Stats
        self.stats = {
            "validations_total": 0,
            "validations_ok": 0,
            "validations_failed": 0,
            "events_validated": 0,
            "last_validation_ns": 0,
            "last_exit_code": 0,
        }

    async def start(self) -> None:
        """Start validator (subscribe to event bus, start flush loop)."""
        if self._running:
            log.warning("TrioRetinaValidator already running")
            return

        if not self.config.enabled:
            log.info("TrioRetinaValidator disabled (config.enabled=False)")
            return

        # Verify WASM exists
        wasm_path = self.config.resolve_wasm_path()
        if not wasm_path.exists():
            log.error(f"WASM applet not found: {wasm_path}")
            log.error(
                "Run: cargo build --target wasm32-unknown-unknown --release in w3bstream/applet"
            )
            return

        log.info(f"Starting TrioRetinaValidator with WASM: {wasm_path}")

        self._running = True

        # Subscribe to event bus if validation is enabled (ingest or flush)
        if self.event_bus and (self.config.validate_on_ingest or self.config.validate_on_flush):
            self._ingest_subscription_id = self.event_bus.subscribe(self._on_event_ingest)

        # Start flush loop if enabled
        if self.config.validate_on_flush:
            self._flush_task = asyncio.create_task(self._flush_loop())

        log.info("TrioRetinaValidator started")

    async def stop(self) -> None:
        """Stop validator."""
        if not self._running:
            return

        self._running = False

        # Cancel flush task
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Unsubscribe from event bus
        if self.event_bus and self._ingest_subscription_id is not None:
            self._ingest_subscription_id()
            self._ingest_subscription_id = None

        # Final flush
        await self._validate_batch()

        log.info("TrioRetinaValidator stopped")

    def _on_event_ingest(self, event: Any) -> None:
        """Callback for event bus subscription; always buffer, validate on ingest if configured."""
        if not (self.config.validate_on_ingest or self.config.validate_on_flush):
            return

        # Convert event to dict
        source_lobe = getattr(event, "source_lobe", None)
        event_type = getattr(event, "type", None)
        event_dict = {
            "event_id": f"{getattr(event, 'session_id', '')}:{getattr(event, 'clock_ns', 0)}",
            "session_id": getattr(event, "session_id", ""),
            "source_lobe": source_lobe.value
            if source_lobe and hasattr(source_lobe, "value")
            else str(source_lobe or ""),
            "event_type": event_type.value
            if event_type and hasattr(event_type, "value")
            else str(event_type or ""),
            "clock_ns": getattr(event, "clock_ns", 0),
            "payload": getattr(event, "payload", {}),
        }

        # Fire and forget on the validator's event loop (don't block ingestion)
        loop = self.event_bus._ws_loop if (self.event_bus and self.event_bus._ws_loop) else None
        if loop:
            asyncio.run_coroutine_threadsafe(self._buffer.add(event_dict), loop)
            if self.config.validate_on_ingest:
                asyncio.run_coroutine_threadsafe(self._validate_batch(), loop)
        else:
            asyncio.create_task(self._buffer.add(event_dict))
            if self.config.validate_on_ingest:
                asyncio.create_task(self._validate_batch())

    async def _flush_loop(self) -> None:
        """Periodic batch validation loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval_s)
                if self._running:
                    await self._validate_batch()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Flush loop error: {e}")

    async def _validate_batch(self) -> ValidationResult | None:
        """Validate current event batch."""
        events = await self._buffer.drain()

        if not events:
            return None

        # Get block number
        try:
            block_number = await self.config.get_block_number()
        except Exception as e:
            log.warning(f"Failed to get block number: {e}")
            block_number = 0

        # Get commitment roots
        visual_root = self.visual_oracle_root_provider()
        posp_root = self.posp_root_provider()

        # Build payload
        payload = build_evm_log_payload(
            session=self.session,
            events=events,
            config=self.config,
            visual_oracle_root=visual_root,
            posp_root=posp_root,
            first_session_id=self.first_session_id,
            device_key=self.device_key,
        )

        # Override block number and enforce the cadence the applet expects
        payload.block_number = (block_number // 64) * 64

        # Run validation
        result = await self.runner.run(payload)

        # Record stats
        self.stats["validations_total"] += 1
        self.stats["events_validated"] += len(events)
        self.stats["last_validation_ns"] = time.time_ns()
        self.stats["last_exit_code"] = result.exit_code

        if result.ok:
            self.stats["validations_ok"] += 1
            log.info(
                f"trio-retina validation ok: exit={result.exit_code} in {result.duration_ms:.1f}ms, events={len(events)}"
            )
        else:
            self.stats["validations_failed"] += 1
            log.warning(
                f"trio-retina validation failed: exit={result.exit_code} ({result.error_description})"
            )

            # Emit anomaly if event bus available
            if self.event_bus:
                self._emit_anomaly(result)

        return ValidationResult(
            ok=result.ok,
            exit_code=result.exit_code,
            error_description=result.error_description,
            duration_ms=result.duration_ms,
            payload=payload,
            events_validated=len(events),
        )

    def _emit_anomaly(self, result: WasmResult) -> None:
        """Emit validation failure as anomaly event."""
        if not self.event_bus:
            return

        try:
            self.event_bus.emit_raw(
                source_lobe=SourceLobe.FUSION,
                event_type="anomaly",
                payload={
                    "anomaly_type": "trio_retina_validation_failure",
                    "exit_code": result.exit_code,
                    "error_description": result.error_description,
                    "payload_hash": result.payload.payload_hash if result.payload else "",
                    "device_id": result.payload.device_id if result.payload else "",
                },
                clock_ns_override=time.time_ns(),
                session_head_ns=self.session.session_head_ns,
            )
        except Exception as e:
            log.error(f"Failed to emit anomaly: {e}")

    async def validate_now(self) -> ValidationResult | None:
        """Trigger immediate validation of current buffer."""
        return await self._validate_batch()

    def get_stats(self) -> dict:
        """Get validator statistics."""
        return dict(self.stats)


def create_validator(
    config: TrioRetinaConfig,
    session: SessionIdentity,
    event_bus: RetinaEventBus | None = None,
    visual_oracle_root_provider: Callable[[], str] | None = None,
    posp_root_provider: Callable[[], str] | None = None,
    first_session_id: str | None = None,
    device_key: bytes | None = None,
) -> TrioRetinaValidator:
    """Factory function to create TrioRetinaValidator."""
    return TrioRetinaValidator(
        config=config,
        session=session,
        event_bus=event_bus,
        visual_oracle_root_provider=visual_oracle_root_provider,
        posp_root_provider=posp_root_provider,
        first_session_id=first_session_id,
        device_key=device_key,
    )
