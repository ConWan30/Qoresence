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
    model: str = "gemini-3.5-flash-lite"
    source: str = "gemini"
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


def _team_keyset(name: str | None) -> set[str]:
    raw = str(name or "").strip()
    if not raw:
        return set()
    try:
        from qoresence.profiles.cfb27_product import _team_keys

        keys = set(_team_keys(raw))
    except Exception:
        keys = set()
    token = re.sub(r"[^A-Z0-9]+", "", raw.upper())
    if token:
        keys.add(token)
    return keys


def side_same(prev: str | None, cur: str | None) -> bool:
    """True when a side is empty or catalog keys overlap (DAL == Dallas == Cowboys)."""
    p = str(prev or "").strip()
    c = str(cur or "").strip()
    if not p or not c:
        return True
    if p.upper() == c.upper():
        return True
    return bool(_team_keyset(p) & _team_keyset(c))


def board_sides_same(
    last_home: str | None,
    last_away: str | None,
    home: str | None,
    away: str | None,
) -> bool:
    return side_same(last_home, home) and side_same(last_away, away)


def resolve_session_id(explicit: str | None = None) -> str:
    """Fill confirm session_id from SessionAuthority when the caller left it empty."""
    s = str(explicit or "").strip()
    if s:
        return s
    try:
        from qoresence.core.session import SessionAuthority

        ident = SessionAuthority.current()
        if ident is not None:
            return str(ident.session_id or "")
    except Exception:
        pass
    return ""


def mint_confirm_ticket(
    *,
    session_id: str,
    clock_ns: int,
    home_score: int | None,
    away_score: int | None,
    model: str = "gemini-3.5-flash-lite",
    source: str = "gemini",
    frame_seq: int | None = None,
    crop_hash: str = "",
    quarter: int | None = None,
    down: int | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
    book: ConfirmTicketBook | None = None,
) -> ConfirmTicket:
    # Normalize and validate source: ONLY seeing-path sources allowed
    normalized_source = normalize_source(source)
    if not is_seeing_source(normalized_source):
        try:
            from qoresence.graphs.ticket_provenance import record_refuse

            record_refuse("vlm_none", session_id=resolve_session_id(session_id))
        except Exception:
            pass
        raise ConfirmTicketSourceError(
            f"Cannot mint ConfirmTicket with source={source!r}. "
            f"Only seeing-path sources {SEEING_PATH_SOURCES} are allowed."
        )

    hs, aws = _norm_int(home_score), _norm_int(away_score)
    q = _norm_int(quarter)
    ht = str(home_team or "").strip()
    at = str(away_team or "").strip()
    sid = resolve_session_id(session_id)

    # Reuse ticket_id when scores + matchup are unchanged. Raw wordmarks flicker
    # (DAL / Dallas / Cowboys / empty). Quarter flicker is not a remint.
    live_book = book if book is not None else get_ticket_book()
    last_identity = live_book.last_board_identity()
    last_ticket = live_book.latest()
    last_hs = last_aws = None
    last_ht = last_at = ""
    if last_identity is not None:
        last_hs, last_aws, last_ht, last_at = last_identity
        if not ht and last_ht:
            ht = last_ht
        if not at and last_at:
            at = last_at

    prior_id = last_ticket.ticket_id if last_ticket is not None else ""
    if (
        last_ticket is not None
        and hs is not None
        and aws is not None
        and hs == last_hs
        and aws == last_aws
        and board_sides_same(last_ht, last_at, ht, at)
    ):
        reused = ConfirmTicket(
            ticket_id=last_ticket.ticket_id,
            session_id=sid,
            clock_ns=int(clock_ns or 0),
            home_score=hs,
            away_score=aws,
            model=str(model or "gemini-3.5-flash-lite"),
            source=normalized_source,
            frame_seq=_norm_int(frame_seq),
            crop_hash=str(crop_hash or ""),
            quarter=q,
            down=_norm_int(down),
        )
        _note_provenance(reused, prior_id)
        return reused

    payload = {
        "v": DOMAIN,
        "session_id": sid,
        "clock_ns": int(clock_ns or 0),
        "home_score": hs,
        "away_score": aws,
        "model": str(model or "gemini-3.5-flash-lite"),
        "source": normalized_source,
        "frame_seq": _norm_int(frame_seq),
        "crop_hash": str(crop_hash or ""),
        "quarter": q,
        "down": _norm_int(down),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ticket_id = hashlib.sha256(raw).hexdigest()[:16]
    fields = {k: v for k, v in payload.items() if k != "v"}
    minted = ConfirmTicket(ticket_id=ticket_id, **fields)
    _note_provenance(minted, prior_id)
    return minted


def _note_provenance(ticket: ConfirmTicket, prior_ticket_id: str) -> None:
    """Record after book reads. Never holds the ticket-book lock. Never emits."""
    try:
        from qoresence.graphs.ticket_provenance import record_mint

        record_mint(ticket, prior_ticket_id=prior_ticket_id)
    except Exception:
        pass


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
        # Track (home_score, away_score, home_team, away_team)
        self._last_board_identity: tuple[int | None, int | None, str, str] | None = None
        self._identity_stale = False

    def put(self, ticket: ConfirmTicket, *, home_team: str = "", away_team: str = "") -> ConfirmTicket:
        with self._lock:
            self._latest = ticket
            self._by_id[ticket.ticket_id] = ticket
            self._last_board_identity = (
                ticket.home_score,
                ticket.away_score,
                str(home_team or "").strip(),
                str(away_team or "").strip(),
            )
            self._identity_stale = False
        return ticket

    def latest(self) -> ConfirmTicket | None:
        with self._lock:
            return self._latest

    def last_board_identity(self) -> tuple[int | None, int | None, str, str] | None:
        with self._lock:
            return self._last_board_identity

    def mark_identity_stale(self) -> None:
        """Loading/cutscene: prior matchup must not license the next board."""
        with self._lock:
            self._identity_stale = True
        try:
            from qoresence.graphs.ticket_provenance import note_identity_stale

            note_identity_stale()
        except Exception:
            pass

    def identity_stale(self) -> bool:
        with self._lock:
            return bool(self._identity_stale)

    def clear(self) -> None:
        with self._lock:
            self._latest = None
            self._by_id.clear()
            self._last_fast = None
            self._last_board_identity = None
            self._identity_stale = False

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
