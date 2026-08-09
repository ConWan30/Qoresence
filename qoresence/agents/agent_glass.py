"""AgentGlass - read-only spectator bridge for external agents."""
from __future__ import annotations
import logging
import threading
import time
from collections import deque
from typing import Any, Callable
log = logging.getLogger(__name__)
_DEFAULT_MAXLEN = 1024

class AgentGlass:
    """Read-only subscriber that curates events for external agents."""
    def __init__(self, *, bus: Any = None, config: Any = None, session_identity: Any = None, situation_provider: Callable[[], dict[str, Any]] | None = None) -> None:
        self.bus = bus
        self.config = config
        self.session_identity = session_identity
        self._situation_provider = situation_provider
        self._lock = threading.RLock()
        maxlen = int(getattr(config, "max_history", _DEFAULT_MAXLEN) or _DEFAULT_MAXLEN) if config else _DEFAULT_MAXLEN
        maxlen = max(256, min(4096, maxlen))
        self._events: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._seq = 0
        self._unsubscribe: Callable[[], None] | None = None
        self._started = False
        self._start_ns = time.monotonic_ns()
    def start(self) -> bool:
        if self._started:
            return True
        if self.bus is None:
            log.warning("AgentGlass start: no bus")
            return False
        try:
            unsub = self.bus.subscribe(self._on_event)  # type: ignore[attr-defined]
            if callable(unsub):
                self._unsubscribe = unsub
            self._started = True
            log.info("AgentGlass started (history=%d)", len(self._events))
            return True
        except Exception as e:
            log.warning("AgentGlass start failed: %s", e)
            return False
    def stop(self) -> None:
        if self._unsubscribe:
            try:
                self._unsubscribe()
            except Exception:
                pass
            self._unsubscribe = None
        self._started = False
        log.info("AgentGlass stopped")
    def is_running(self) -> bool:
        return bool(self._started)
    def _on_event(self, event: Any) -> None:
        try:
            if hasattr(event, "to_dict"):
                d = event.to_dict()
            elif isinstance(event, dict):
                d = dict(event)
            else:
                d = {"payload": getattr(event, "payload", {}), "type": str(getattr(event, "type", "unknown"))}
            with self._lock:
                self._seq += 1
                d["_agent_seq"] = self._seq
                self._events.append(d)
        except Exception as e:
            log.debug("AgentGlass _on_event error: %s", e)
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            seq = self._seq
            events_count = len(self._events)
            last_types = [e.get("type", "?") for e in list(self._events)[-5:]]
        coupling: dict[str, Any] = {}
        try:
            from qoresence.sync.ivc import get_last_coupling
            coupling = get_last_coupling()
        except Exception:
            coupling = {"coupling": 0.0, "frame_seq": 0}
        video: dict[str, Any] = {"has_frame": False}
        try:
            from qoresence.vision.clip_buffer import get_clip_buffer
            video = get_clip_buffer().stats()
        except Exception:
            pass
        situation: dict[str, Any] = {}
        if self._situation_provider:
            try:
                situation = self._situation_provider() or {}
            except Exception:
                situation = {}
        bus_stats: dict[str, Any] = {}
        if self.bus is not None and hasattr(self.bus, "stats"):
            try:
                bus_stats = self.bus.stats()
            except Exception:
                pass
        session: dict[str, Any] = {}
        if self.session_identity is not None:
            try:
                session = self.session_identity.to_dict()  # type: ignore[union-attr]
            except Exception:
                session = {"session_id": getattr(self.session_identity, "session_id", "")}
        elif self.bus is not None:
            session = {"session_id": getattr(self.bus, "session_id", "")}
        uptime_s = (time.monotonic_ns() - self._start_ns) / 1e9 if self._start_ns else 0.0
        return {"ok": True, "enabled": True, "session": session, "situation": situation, "coupling": coupling, "video": video, "bus": bus_stats, "events_count": events_count, "seq": seq, "last_types": last_types, "uptime_s": round(uptime_s, 1), "clock_ns": time.monotonic_ns()}
    def get_events(self, *, since: int = 0, types: list[str] | None = None, limit: int = 100) -> dict[str, Any]:
        limit = max(1, min(500, int(limit)))
        since = max(0, int(since))
        want = set(types) if types else None
        out: list[dict[str, Any]] = []
        with self._lock:
            for e in list(self._events):
                seq = int(e.get("_agent_seq", 0))
                if seq <= since:
                    continue
                if want and str(e.get("type", "")) not in want:
                    continue
                out.append(e)
                if len(out) >= limit:
                    break
            next_seq = self._seq
        return {"ok": True, "events": out, "next_seq": next_seq, "count": len(out)}
    def health(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {"ok": True, "enabled": True, "running": self._started, "seq": snap.get("seq", 0), "events_count": snap.get("events_count", 0), "video": snap.get("video", {}), "coupling": snap.get("coupling", {}), "bus_clients": snap.get("bus", {}).get("ws_clients", 0), "uptime_s": snap.get("uptime_s", 0)}
_glass: AgentGlass | None = None
_glass_lock = threading.Lock()
def get_agent_glass() -> AgentGlass | None:
    return _glass
def start_agent_glass(*, bus: Any = None, config: Any = None, session_identity: Any = None, situation_provider: Callable[[], dict[str, Any]] | None = None) -> AgentGlass | None:
    global _glass
    with _glass_lock:
        if _glass is not None:
            try:
                _glass.stop()
            except Exception:
                pass
        _glass = AgentGlass(bus=bus, config=config, session_identity=session_identity, situation_provider=situation_provider)
        _glass.start()
        return _glass
def stop_agent_glass() -> None:
    global _glass
    with _glass_lock:
        if _glass is not None:
            try:
                _glass.stop()
            except Exception:
                pass
            _glass = None
def register_situation_provider(provider: Callable[[], dict[str, Any]] | None) -> None:
    g = get_agent_glass()
    if g is not None:
        g._situation_provider = provider  # type: ignore[attr-defined]
