"""Coupling ticket — licenses heat-speech from a live play-phrase.

Observation plane only. Twin of ``QORESENCE-CONFIRM-TICKET-v0``:
confirm tickets license score digits; these license pad-heat talk.
Compose, never conflate. Not a humanity proof.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any

from qoresence.sync.play_phrase import LIVE_PHRASES

DOMAIN = "QORESENCE-COUPLING-TICKET-v0"
DEFAULT_TTL_NS = int(400 * 1e6)

# Speech that claims pad↔picture alignment
HEAT_RE = re.compile(
    r"controller heat|pad and picture|input spike|pad heat|hands? and picture",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CouplingTicket:
    ticket_id: str
    clock_ns: int
    frame_seq: int | None
    phrase: str
    coupling: float
    hold_energy: float
    imu_bodied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def mint_coupling_ticket(
    *,
    clock_ns: int,
    frame_seq: int | None,
    phrase: str,
    coupling: float,
    hold_energy: float,
    imu_bodied: bool = False,
    pll_lock: bool = False,
    video_fresh: bool = True,
    same_seq: bool | None = None,
    plane_dim: bool = False,
) -> CouplingTicket | None:
    """Mint only for live phrases with PLL lock and fresh video.

    Fail-closed: IDLE/HUDDLE/unknown, unlocked PLL, or stale video → None.
    When ``--look-graphs`` Same-Seq is on, seq_skew / plane_dim also refuse.
    """
    ph = str(phrase or "").upper()
    if ph not in LIVE_PHRASES:
        return None
    if not pll_lock or not video_fresh:
        return None
    try:
        from qoresence.graphs.same_seq_join import coupling_mint_allowed

        if not coupling_mint_allowed(
            same_seq=same_seq,
            plane_dim=plane_dim,
            live_seq=int(frame_seq) if frame_seq is not None else 0,
            widget_seq=int(frame_seq) if frame_seq is not None else 0,
        ):
            return None
    except Exception:
        pass
    payload = {
        "v": DOMAIN,
        "clock_ns": int(clock_ns or 0),
        "frame_seq": int(frame_seq) if frame_seq is not None else None,
        "phrase": ph,
        "coupling": round(float(coupling or 0.0), 4),
        "hold_energy": round(float(hold_energy or 0.0), 4),
        "imu_bodied": bool(imu_bodied),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ticket_id = hashlib.sha256(raw).hexdigest()[:16]
    fields = {k: v for k, v in payload.items() if k != "v"}
    return CouplingTicket(ticket_id=ticket_id, **fields)


def heat_speech(text: str) -> bool:
    return bool(text) and bool(HEAT_RE.search(text))


def license_heat_text(text: str, *, ticket: CouplingTicket | None) -> str:
    """Keep heat-speech only when a live coupling ticket is cited."""
    if not text:
        return text
    if not heat_speech(text):
        return text
    if ticket is None:
        return ""
    return text


def why_strip_coupling(ticket: CouplingTicket | None) -> str:
    if ticket is None:
        return "couple: none"
    seq = f" seq={ticket.frame_seq}" if ticket.frame_seq is not None else ""
    return f"couple {ticket.phrase} ticket={ticket.ticket_id}{seq}"


class CouplingTicketBook:
    def __init__(self, ttl_ns: int = DEFAULT_TTL_NS) -> None:
        self._lock = threading.Lock()
        self._latest: CouplingTicket | None = None
        self._by_id: dict[str, CouplingTicket] = {}
        self.ttl_ns = int(ttl_ns)

    def put(self, ticket: CouplingTicket | None) -> CouplingTicket | None:
        if ticket is None:
            return None
        with self._lock:
            self._latest = ticket
            self._by_id[ticket.ticket_id] = ticket
        return ticket

    def expire(self) -> None:
        with self._lock:
            self._latest = None

    def latest(self) -> CouplingTicket | None:
        with self._lock:
            return self._latest

    def latest_live(self, now_ns: int | None = None) -> CouplingTicket | None:
        now = int(now_ns) if now_ns is not None else time.monotonic_ns()
        with self._lock:
            t = self._latest
            if t is None:
                return None
            age = now - int(t.clock_ns)
            if age < 0 or age > self.ttl_ns:
                return None
            return t

    def get(self, ticket_id: str | None) -> CouplingTicket | None:
        if not ticket_id:
            return None
        with self._lock:
            return self._by_id.get(str(ticket_id))


_book = CouplingTicketBook()
_book_lock = threading.Lock()


def get_coupling_book() -> CouplingTicketBook:
    return _book


def reset_coupling_book() -> None:
    global _book
    with _book_lock:
        _book = CouplingTicketBook()
