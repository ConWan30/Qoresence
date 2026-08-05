"""
Qoresence Event Bus — Phase 2

Central event bus that all lobes publish to.
Enforces: session_id + clock_ns + source_lobe on every event.
Outputs: JSONL file + WebSocket server (default 127.0.0.1:8765)
Optional: trio-retina w3bstream validation
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Optional
import weakref

from .types import BaseEvent, SourceLobe, clock_ns

log = logging.getLogger(__name__)

# Optional trio-retina integration
try:
    from qoresence.trio import TrioRetinaConfig, TrioRetinaValidator, create_validator
    from qoresence.core import SessionIdentity
    TRIO_AVAILABLE = True
except ImportError:
    TRIO_AVAILABLE = False
    TrioRetinaConfig = None  # type: ignore
    TrioRetinaValidator = None  # type: ignore
    create_validator = None  # type: ignore
    SessionIdentity = None  # type: ignore


class RetinaEventBus:
    """
    Thread-safe event bus for Qoresence lobes.

    - Enforces required fields (session_id, clock_ns, source_lobe)
    - Writes JSONL to disk (append-only)
    - Serves WebSocket for real-time consumers (OBS overlay, etc.)
    - In-process subscribers for lobe-to-lobe communication
    """

    def __init__(
        self,
        session_id: str,
        jsonl_path: Optional[Path] = None,
        ws_host: str = "127.0.0.1",
        ws_port: int = 8765,
        enable_ws: bool = True,
        max_ws_history: int = 256,
        # Trio-retina validation
        trio_config: Optional["TrioRetinaConfig"] = None,
        session_identity: Optional["SessionIdentity"] = None,
        visual_oracle_root_provider: Optional[Callable[[], str]] = None,
        posp_root_provider: Optional[Callable[[], str]] = None,
        first_session_id: Optional[str] = None,
        device_key: Optional[bytes] = None,
    ):
        self.session_id = session_id
        self.jsonl_path = jsonl_path
        self.ws_host = ws_host
        self.ws_port = ws_port
        self.enable_ws = enable_ws
        self.max_ws_history = max_ws_history

        # Thread-safe subscribers
        self._subscribers: list[Callable[[BaseEvent], None]] = []
        self._sub_lock = threading.Lock()

        # WebSocket state
        self._ws_clients: set = set()
        self._ws_history: deque = deque(maxlen=max_ws_history)
        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws_server: Optional[asyncio.Server] = None
        self._ws_task: Optional[asyncio.Task] = None

        # JSONL writer
        self._jsonl_lock = threading.Lock()
        if jsonl_path:
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)

        # Stats
        self.events_emitted = 0
        self.events_rejected = 0

        # Trio-retina validator (optional)
        self._trio_validator: Optional["TrioRetinaValidator"] = None
        self._trio_config = trio_config
        self._session_identity = session_identity
        self._visual_oracle_root_provider = visual_oracle_root_provider
        self._posp_root_provider = posp_root_provider
        self._first_session_id = first_session_id
        self._device_key = device_key

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def emit(self, event: BaseEvent) -> bool:
        """
        Emit an event to the bus.

        Validates required fields. Returns True if accepted, False if rejected.
        """
        # Validate required fields
        errors = event.validate()
        if errors:
            log.warning(f"Event rejected: {errors}")
            self.events_rejected += 1
            return False

        # Enforce session_id matches bus session
        if event.session_id != self.session_id:
            log.warning(f"Event session_id mismatch: {event.session_id} != {self.session_id}")
            self.events_rejected += 1
            return False

        # Ensure clock_ns is set (monotonic)
        if event.clock_ns <= 0:
            event.clock_ns = clock_ns()

        # Write to JSONL
        if self.jsonl_path:
            self._write_jsonl(event)

        # Notify in-process subscribers
        self._notify_subscribers(event)

        # Queue for WebSocket
        if self.enable_ws:
            self._queue_ws(event)

        self.events_emitted += 1
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # TRIO-RETINA VALIDATION
    # ──────────────────────────────────────────────────────────────────────────

    def init_trio_validator(self) -> bool:
        """
        Initialize trio-retina validator if configured.
        
        Returns True if validator was created, False if not available or disabled.
        """
        if not TRIO_AVAILABLE:
            log.debug("trio-retina not available (install qoresence[trio])")
            return False
        
        if not self._trio_config or not self._trio_config.enabled:
            log.debug("trio-retina validation disabled")
            return False
        
        if not self._session_identity:
            log.warning("trio-retina requires session_identity")
            return False
        
        try:
            self._trio_validator = create_validator(
                config=self._trio_config,
                session=self._session_identity,
                event_bus=self,
                visual_oracle_root_provider=self._visual_oracle_root_provider,
                posp_root_provider=self._posp_root_provider,
                first_session_id=self._first_session_id,
                device_key=self._device_key,
            )
            log.info("trio-retina validator initialized")
            return True
        except Exception as e:
            log.error(f"Failed to initialize trio-retina validator: {e}")
            return False

    async def start_trio_validator(self) -> bool:
        """Start trio-retina validator (must call init_trio_validator first)."""
        if self._trio_validator:
            await self._trio_validator.start()
            return True
        return False

    async def stop_trio_validator(self) -> None:
        """Stop trio-retina validator."""
        if self._trio_validator:
            await self._trio_validator.stop()
            self._trio_validator = None

    def get_trio_stats(self) -> dict[str, Any]:
        """Get trio-retina validator statistics."""
        if self._trio_validator:
            return self._trio_validator.get_stats()
        return {"enabled": False}

    async def trigger_trio_validation(self) -> Optional[dict]:
        """Trigger immediate trio-retina validation of buffered events."""
        if self._trio_validator:
            result = await self._trio_validator.validate_now()
            if result:
                return {
                    "ok": result.ok,
                    "exit_code": result.exit_code,
                    "error_description": result.error_description,
                    "duration_ms": result.duration_ms,
                    "events_validated": result.events_validated,
                }
        return None

    def emit_raw(
        self,
        source_lobe: SourceLobe,
        event_type: str,
        payload: dict[str, Any],
        clock_ns_override: Optional[int] = None,
        session_head_ns: Optional[int] = None,
    ) -> bool:
        """
        Emit a raw event (convenience method).

        Creates BaseEvent internally with current clock_ns.
        """
        from .types import BaseEvent, EventType

        try:
            etype = EventType(event_type)
        except ValueError:
            log.warning(f"Unknown event type: {event_type}")
            self.events_rejected += 1
            return False

        event = BaseEvent(
            session_id=self.session_id,
            clock_ns=clock_ns_override or clock_ns(),
            source_lobe=source_lobe,
            type=etype,
            payload=payload,
            session_head_ns=session_head_ns,
        )
        return self.emit(event)

    def subscribe(self, callback: Callable[[BaseEvent], None]) -> Callable[[], None]:
        """
        Subscribe to events in-process.

        Returns an unsubscribe function.
        """
        with self._sub_lock:
            self._subscribers.append(callback)

        def unsubscribe():
            with self._sub_lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    # ──────────────────────────────────────────────────────────────────────────
    # JSONL OUTPUT
    # ──────────────────────────────────────────────────────────────────────────

    def _write_jsonl(self, event: BaseEvent) -> None:
        """Write event to JSONL file (thread-safe)."""
        try:
            with self._jsonl_lock:
                with self.jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event.to_dict(), separators=(",", ":")) + "\n")
        except Exception as e:
            log.error(f"JSONL write failed: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # IN-PROCESS SUBSCRIBERS
    # ──────────────────────────────────────────────────────────────────────────

    def _notify_subscribers(self, event: BaseEvent) -> None:
        """Notify all in-process subscribers."""
        with self._sub_lock:
            subs = list(self._subscribers)

        for cb in subs:
            try:
                cb(event)
            except Exception as e:
                log.error(f"Subscriber error: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # WEBSOCKET SERVER
    # ──────────────────────────────────────────────────────────────────────────

    def _queue_ws(self, event: BaseEvent) -> None:
        """Queue event for WebSocket broadcast."""
        self._ws_history.append(event.to_dict())
        if self._ws_loop and self._ws_clients:
            asyncio.run_coroutine_threadsafe(self._broadcast_ws(event.to_dict()), self._ws_loop)

    async def _broadcast_ws(self, msg: dict[str, Any]) -> None:
        """Broadcast message to all WebSocket clients."""
        dead = set()
        msg_str = json.dumps(msg, separators=(",", ":"))
        for ws in self._ws_clients:
            try:
                await ws.send(msg_str)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._ws_clients.discard(ws)

    async def _ws_handler(self, websocket) -> None:
        """Handle a WebSocket connection."""
        self._ws_clients.add(websocket)
        log.info(f"WS client connected: {websocket.remote_address}")

        # Replay recent history
        for msg in list(self._ws_history)[-32:]:
            try:
                await websocket.send(json.dumps(msg, separators=(",", ":")))
            except Exception:
                break

        try:
            async for _ in websocket:
                pass  # Ignore incoming messages for now
        finally:
            self._ws_clients.discard(websocket)
            log.info(f"WS client disconnected")

    def start_ws(self) -> None:
        """Start WebSocket server in background thread."""
        if not self.enable_ws:
            return

        try:
            import websockets
        except ImportError:
            log.warning("websockets package not installed, WebSocket disabled")
            self.enable_ws = False
            return

        def _run_ws():
            self._ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._ws_loop)

            async def _start():
                self._ws_server = await websockets.serve(
                    self._ws_handler,
                    self.ws_host,
                    self.ws_port,
                )
                log.info(f"WebSocket server started on ws://{self.ws_host}:{self.ws_port}")

            self._ws_loop.run_until_complete(_start())
            self._ws_loop.run_forever()

        self._ws_thread = threading.Thread(target=_run_ws, name="qoresence-ws", daemon=True)
        self._ws_thread.start()

    def stop_ws(self) -> None:
        """Stop WebSocket server."""
        if self._ws_loop and self._ws_server:
            self._ws_loop.call_soon_threadsafe(self._ws_server.close)
        if self._ws_loop:
            self._ws_loop.call_soon_threadsafe(self._ws_loop.stop)

    # ──────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the bus (WebSocket server)."""
        if self.enable_ws:
            self.start_ws()

    def stop(self) -> None:
        """Stop the bus."""
        self.stop_ws()
        # Note: trio validator stop is async, caller should call stop_trio_validator() before stop()
        # We can't await here, but we can schedule if there's a running loop
        if self._trio_validator and self._ws_loop and self._ws_loop.is_running():
            asyncio.run_coroutine_threadsafe(self._trio_validator.stop(), self._ws_loop)

    def stats(self) -> dict[str, Any]:
        """Return bus statistics."""
        stats = {
            "session_id": self.session_id,
            "events_emitted": self.events_emitted,
            "events_rejected": self.events_rejected,
            "ws_clients": len(self._ws_clients),
            "ws_history_size": len(self._ws_history),
        }
        if self._trio_validator:
            stats["trio_retina"] = self._trio_validator.get_stats()
        return stats


# ──────────────────────────────────────────────────────────────────────────────
# MULTI-SESSION BUS MANAGER (for future multi-session support)
# ──────────────────────────────────────────────────────────────────────────────

class EventBusManager:
    """
    Manages multiple RetinaEventBus instances (one per session).
    """

    def __init__(self):
        self._buses: dict[str, RetinaEventBus] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        session_id: str,
        jsonl_path: Optional[Path] = None,
        ws_host: str = "127.0.0.1",
        ws_port: int = 8765,
        enable_ws: bool = True,
    ) -> RetinaEventBus:
        with self._lock:
            if session_id not in self._buses:
                bus = RetinaEventBus(
                    session_id=session_id,
                    jsonl_path=jsonl_path,
                    ws_host=ws_host,
                    ws_port=ws_port,
                    enable_ws=enable_ws,
                )
                self._buses[session_id] = bus
            return self._buses[session_id]

    def get(self, session_id: str) -> Optional[RetinaEventBus]:
        with self._lock:
            return self._buses.get(session_id)

    def remove(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._buses:
                self._buses[session_id].stop()
                del self._buses[session_id]
                return True
            return False

    def all_stats(self) -> dict[str, Any]:
        with self._lock:
            return {sid: bus.stats() for sid, bus in self._buses.items()}