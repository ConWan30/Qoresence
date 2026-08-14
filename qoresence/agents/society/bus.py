"""Publish receipts to an in-process sink; optional SessionTimeline mirror."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from .types import AgentReceipt

log = logging.getLogger(__name__)

_KIND = {
    "note": "society_note",
    "veto": "society_veto",
    "allow": "society_note",
    "advise": "society_note",
    "propose_cut": "society_propose_cut",
    "audit": "society_audit",
}


class SocietyBus:
    def __init__(self, *, mirror_timeline: bool = True, max_n: int = 64) -> None:
        self.mirror_timeline = mirror_timeline
        self._recent: deque[dict[str, Any]] = deque(maxlen=max_n)

    def publish(self, receipt: AgentReceipt) -> None:
        if receipt.ts_ns <= 0:
            receipt.ts_ns = time.monotonic_ns()
        d = receipt.to_dict()
        self._recent.append(d)
        if not self.mirror_timeline:
            return
        try:
            from qoresence.agents.session_timeline import get_session_timeline

            kind = _KIND.get(receipt.action, "society_note")
            get_session_timeline().append(
                kind=kind,
                path="society",
                message=(receipt.text or "")[:160],
                reason=receipt.role,
                payload={"receipt": d},
                clock_ns=receipt.ts_ns,
            )
        except Exception as e:
            log.debug("society timeline mirror skipped: %s", e)

    def recent(self, n: int = 12) -> list[dict[str, Any]]:
        return list(self._recent)[-n:]
