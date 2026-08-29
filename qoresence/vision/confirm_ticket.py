"""Confirm ticket — DeepSeek visual lock that licenses score speech.

Observation plane only. Not a humanity proof. Not a chain receipt.
Nemotron / Society / confirm-chat may emit score digits only when they
cite a live ticket minted from a DeepSeek board lock.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import asdict, dataclass
from typing import Any

DOMAIN = "QORESENCE-CONFIRM-TICKET-v0"
SCORE_PAIR = re.compile(r"\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\b")

# Seeing-path sources (VLM / OCR scorebug) that license score_vlm_locked
SEEING_PATH_SOURCES = frozenset({"deepseek", "gemini", "quicksilver", "easyocr_scorebug"})

# Source aliases for normalization
SOURCE_ALIASES = {
    "deepseek_scoreboard": "deepseek",
    "deepseek-vlm": "deepseek",
    "ds-vision": "deepseek",
    "gemini_scoreboard": "gemini",
    "qs": "quicksilver",
    "easyocr": "easyocr_scorebug",
    "paddle": "easyocr_scorebug",
}


class ConfirmTicketSourceError(ValueError):
    """Raised when attempting to mint a ticket from a non-seeing-path source."""

    pass


def normalize_source(source: str | None) -> str:
    """Normalize source aliases to canonical form."""
    if not source:
        return ""
    s = str(source).strip().lower()
    return SOURCE_ALIASES.get(s, s)


def is_seeing_source(source: str | None) -> bool:
    """Return True if source is a seeing-path source (VLM / OCR scorebug)."""
    if not source:
        return False
    s = normalize_source(source)
    return s in SEEING_PATH_SOURCES


@dataclass(frozen=True)
class ConfirmTicket:
    ticket_id: str
    session_id: str
    clock_ns: int
    home_score: int | None
    away_score: int | None
    model: str = "deepseek-v4-flash-vision-exp"
    source: str = "deepseek"
    frame_seq: int | None = None
    crop_hash: str = ""
    quarter: int | None = None
    down: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def mint_confirm_ticket(
    *,
    session_id: str,
    clock_ns: int,
    home_score: int | None,
    away_score: int | None,
    model: str = "deepseek-v4-flash-vision-exp",
    source: str = "deepseek",
    frame_seq: int | None = None,
    crop_hash: str = "",
    quarter: int | None = None,
    down: int | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
) -> ConfirmTicket:
    # Normalize and validate source: ONLY seeing-path sources allowed
    normalized_source = normalize_source(source)
    if not is_seeing_source(normalized_source):
        raise ConfirmTicketSourceError(
            f"Cannot mint ConfirmTicket with source={source!r}. "
            f"Only seeing-path sources {SEEING_PATH_SOURCES} are allowed."
        )
    
    hs, aws = _norm_int(home_score), _norm_int(away_score)
    # Hash payload excludes clock_ns but INCLUDES identity (home/away team)
    # Operator intent: DAL 27-0 and IND 27-0 must be different tickets
    # Mint only when home/away/identity/quarter change or lock drops
    hash_payload = {
        "v": DOMAIN,
        "session_id": str(session_id or ""),
        "home_score": hs,
        "away_score": aws,
        "home_team": str(home_team or "").strip().upper(),
        "away_team": str(away_team or "").strip().upper(),
        "model": str(model or "deepseek-v4-flash-vision-exp"),
        "source": normalized_source,
        "quarter": _norm_int(quarter),
        "down": _norm_int(down),
    }
    raw = json.dumps(hash_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ticket_id = hashlib.sha256(raw).hexdigest()[:16]
    
    # Full ticket includes clock_ns (for display/debug), but not in hash
    return ConfirmTicket(
        ticket_id=ticket_id,
        session_id=str(session_id or ""),
        clock_ns=int(clock_ns or 0),
        home_score=hs,
        away_score=aws,
        model=str(model or "deepseek-v4-flash-vision-exp"),
        source=normalized_source,
        frame_seq=_norm_int(frame_seq),
        crop_hash=str(crop_hash or ""),
        quarter=_norm_int(quarter),
        down=_norm_int(down),
    )


def license_score_text(
    text: str,
    *,
    ticket: ConfirmTicket | None,
    home_score: int | None = None,
    away_score: int | None = None,
) -> str:
    """Keep a score pair only when a ticket exists and the digits match the board."""
    if not text:
        return text
    hs = _norm_int(home_score if ticket is None else ticket.home_score)
    aws = _norm_int(away_score if ticket is None else ticket.away_score)

    def _keep(m: re.Match[str]) -> str:
        if ticket is None:
            return "board"
        try:
            a, b = int(m.group(1)), int(m.group(2))
        except (TypeError, ValueError):
            return "board"
        if hs is not None and aws is not None and {a, b} == {hs, aws}:
            return m.group(0)
        return "board"

    return SCORE_PAIR.sub(_keep, text)


def why_strip(ticket: ConfirmTicket | None, last_fast: dict[str, Any] | None = None) -> str:
    if ticket is None:
        return "confirm: none"
    line = f"confirm {ticket.home_score}-{ticket.away_score} ticket={ticket.ticket_id}"
    if ticket.frame_seq is not None:
        line += f" seq={ticket.frame_seq}"
    if last_fast:
        kind = str(last_fast.get("kind") or last_fast.get("action") or "fast")
        line += f" · last fast={kind}"
    return line


def mismatch_snapshot(
    *,
    last_fast: dict[str, Any] | None,
    last_confirm: ConfirmTicket | None,
) -> dict[str, Any]:
    fast = dict(last_fast or {})
    confirm = last_confirm.to_dict() if last_confirm is not None else None
    lag = None
    if last_confirm is not None and fast.get("clock_ns") is not None:
        try:
            lag = int(last_confirm.clock_ns) - int(fast["clock_ns"])
        except (TypeError, ValueError):
            lag = None
    return {"last_fast": fast or None, "last_confirm": confirm, "lag_ns": lag}


class ConfirmTicketBook:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: ConfirmTicket | None = None
        self._by_id: dict[str, ConfirmTicket] = {}
        self._last_fast: dict[str, Any] | None = None

    def put(self, ticket: ConfirmTicket) -> ConfirmTicket:
        with self._lock:
            self._latest = ticket
            self._by_id[ticket.ticket_id] = ticket
        return ticket

    def latest(self) -> ConfirmTicket | None:
        with self._lock:
            return self._latest

    def get(self, ticket_id: str | None) -> ConfirmTicket | None:
        if not ticket_id:
            return None
        with self._lock:
            return self._by_id.get(str(ticket_id))

    def note_fast(self, event: dict[str, Any] | None) -> None:
        if not event:
            return
        with self._lock:
            self._last_fast = dict(event)

    def last_fast(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._last_fast) if self._last_fast else None

    def mismatch(self) -> dict[str, Any]:
        return mismatch_snapshot(last_fast=self.last_fast(), last_confirm=self.latest())


_BOOK = ConfirmTicketBook()


def get_ticket_book() -> ConfirmTicketBook:
    return _BOOK
