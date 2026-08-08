"""In-process A2A bus with optional RetinaEventBus mirror."""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

from qoresence.a2a.types import A2AMessage

log = logging.getLogger(__name__)


class A2ABus:
    """Thread-safe in-process pub/sub for A2A messages."""

    def __init__(self, capacity: int = 200) -> None:
        self._lock = threading.Lock()
        self._subs: list[Callable[[A2AMessage], None]] = []
        self._recent: deque[A2AMessage] = deque(maxlen=capacity)
        self._retina_bus: Any = None
        self._session_id: str | None = None

    def set_retina_mirror(self, bus: Any, session_id: str | None = None) -> None:
        self._retina_bus = bus
        self._session_id = session_id

    def subscribe(self, cb: Callable[[A2AMessage], None]) -> Callable[[], None]:
        with self._lock:
            self._subs.append(cb)

        def _unsub() -> None:
            with self._lock:
                if cb in self._subs:
                    self._subs.remove(cb)

        return _unsub

    def publish(self, msg: A2AMessage) -> None:
        with self._lock:
            if self._session_id and not msg.session_id:
                msg.session_id = self._session_id
            self._recent.append(msg)
            subs = list(self._subs)
        for cb in subs:
            try:
                cb(msg)
            except Exception as e:
                log.debug("A2A subscriber error: %s", e)
        # Optional mirror — only commit_act reaches the deck feed as human text.
        # Intermediate scene/chat proposals stay on the A2A bus only.
        if self._retina_bus is not None and msg.kind == "commit_act":
            try:
                from qoresence.core import SourceLobe

                body = msg.body if isinstance(msg.body, dict) else {}
                text = str(body.get("text") or body.get("message") or "").strip()
                if not text:
                    return
                self._retina_bus.emit_raw(
                    source_lobe=SourceLobe.AGENT,
                    event_type="agent_action",
                    payload={
                        "agent_name": "a2a",
                        "action": "chat",
                        "message": text[:200],
                        "reason": str(body.get("reason") or "a2a_commit")[:120],
                        "path": str(body.get("path") or "fast"),
                        "evidence": body.get("evidence"),
                        "a2a": msg.to_dict(),
                    },
                    clock_ns_override=msg.clock_ns,
                )
            except Exception:
                pass

    def emit_evidence(self, evidence: dict[str, Any], clock_ns: int | None = None) -> None:
        """Emit an evidence chain event to the RetinaEventBus (Trio P4)."""
        if self._retina_bus is None:
            return
        try:
            from qoresence.core import SourceLobe

            self._retina_bus.emit_raw(
                source_lobe=SourceLobe.AGENT,
                event_type="evidence_chain",
                payload=evidence,
                clock_ns_override=clock_ns,
            )
        except Exception as e:
            log.debug("A2A evidence emit failed: %s", e)

    def emit_router_decision(self, decision: dict[str, Any], clock_ns: int | None = None) -> None:
        """Emit a router decision log to the RetinaEventBus (Trio P2)."""
        if self._retina_bus is None:
            return
        try:
            from qoresence.core import SourceLobe

            self._retina_bus.emit_raw(
                source_lobe=SourceLobe.AGENT,
                event_type="router_decision",
                payload=decision,
                clock_ns_override=clock_ns,
            )
        except Exception as e:
            log.debug("A2A router decision emit failed: %s", e)

    def recent(self, n: int = 20) -> list[A2AMessage]:
        with self._lock:
            items = list(self._recent)
        return items[-n:] if n > 0 else items

    def stats(self) -> dict[str, Any]:
        with self._lock:
            commits = sum(1 for m in self._recent if m.kind == "commit_act")
            vetos = sum(1 for m in self._recent if m.kind == "veto")
            return {
                "messages": len(self._recent),
                "commits": commits,
                "vetos": vetos,
                "subscribers": len(self._subs),
            }
