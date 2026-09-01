"""Ticket provenance DAG — mint / reuse / remint / refuse license the next confirm.

Nodes carry ticket_id + clock + source + crop_hash + frame_seq. No score fields.
Record after ConfirmTicketBook / mint reads release. Never emit_raw.
"""

from __future__ import annotations

import threading
from typing import Any

from qoresence.graphs.flags import graph_enabled, note_applied
from qoresence.graphs.look_license import LookLicense, append_license, make_license
from qoresence.vision.board_why import BOARD_WHY_UNLOCKED, normalize_board_why

EDGE_KINDS = frozenset({"mint", "reuse", "remint", "refuse"})
IDENTITY_REFUSE = frozenset({"refuse_zero_zero", "refuse_identity_swap"})

_lock = threading.Lock()
_last_kind: str = ""
_last_ticket_id: str = ""
_last_crop_hash: str = ""
_last_why: str = ""
_identity_blocked: bool = False
_last_license: LookLicense | None = None


def reset() -> None:
    global _last_kind, _last_ticket_id, _last_crop_hash, _last_why
    global _identity_blocked, _last_license
    with _lock:
        _last_kind = ""
        _last_ticket_id = ""
        _last_crop_hash = ""
        _last_why = ""
        _identity_blocked = False
        _last_license = None


def note_identity_stale() -> None:
    """Caller already released the ticket-book lock."""
    if not graph_enabled("ticket_provenance"):
        return
    global _identity_blocked
    with _lock:
        _identity_blocked = True


def record_edge(
    kind: str,
    *,
    ticket_id: str = "",
    clock_ns: int | None = None,
    session_id: str = "",
    source: str = "",
    crop_hash: str = "",
    frame_seq: int | None = None,
    why: str = "",
    prior_ticket_id: str = "",
) -> LookLicense | None:
    """Record a provenance edge and return the next-look license. Flag off → None."""
    global _last_kind, _last_ticket_id, _last_crop_hash, _last_why
    global _identity_blocked, _last_license
    if not graph_enabled("ticket_provenance"):
        return None
    edge = str(kind or "").strip()
    if edge not in EDGE_KINDS:
        return None
    why_tok = normalize_board_why(why) if why else ""
    if edge == "refuse" and why_tok and why_tok == _last_why and _last_kind == "refuse":
        return _last_license

    keep_crop = bool(edge == "remint" and crop_hash and crop_hash == _last_crop_hash)
    reuse_identity = edge in {"reuse", "mint"}
    if edge == "refuse" and (why_tok in IDENTITY_REFUSE or _identity_blocked):
        reuse_identity = False
    if edge == "reuse":
        next_action = "keep"
    elif edge == "remint":
        next_action = "remint"
    elif edge == "mint":
        next_action = "mint"
    else:
        next_action = "refuse"

    permits: dict[str, Any] = {
        "next_action": next_action,
        "keep_crop": keep_crop,
        "reuse_identity": reuse_identity,
    }
    refuses: list[str] = []
    if edge == "refuse":
        if why_tok:
            refuses.append(why_tok)
        if _identity_blocked or why_tok in IDENTITY_REFUSE:
            refuses.append("identity_stale")
            permits["reuse_identity"] = False

    lic = make_license(
        graph="ticket_provenance",
        kind=edge,
        session_id=session_id,
        clock_ns=clock_ns,
        permits=permits,
        refuses=tuple(refuses),
        source_ticket_id=ticket_id,
        frame_seq=frame_seq,
        crop_hash=crop_hash,
    )
    if lic is None:
        return None

    with _lock:
        _last_kind = edge
        if ticket_id:
            _last_ticket_id = ticket_id
        if crop_hash:
            _last_crop_hash = crop_hash
        if why_tok:
            _last_why = why_tok
        if edge == "remint":
            _identity_blocked = False
        if edge == "refuse" and (why_tok in IDENTITY_REFUSE):
            _identity_blocked = True
        _last_license = lic
    # lock released before JSONL
    append_license(lic)
    note_applied(lic.id)
    return lic


def record_mint(
    ticket: Any,
    *,
    prior_ticket_id: str = "",
    prior_crop_hash: str = "",
) -> LookLicense | None:
    """Classify mint vs reuse vs remint from a ConfirmTicket. Call after book reads."""
    if not graph_enabled("ticket_provenance"):
        return None
    if ticket is None:
        return None
    tid = str(getattr(ticket, "ticket_id", "") or "")
    prior = str(prior_ticket_id or "")
    if prior and tid == prior:
        kind = "reuse"
    elif prior:
        kind = "remint"
    else:
        kind = "mint"
    return record_edge(
        kind,
        ticket_id=tid,
        clock_ns=getattr(ticket, "clock_ns", None),
        session_id=str(getattr(ticket, "session_id", "") or ""),
        source=str(getattr(ticket, "source", "") or ""),
        crop_hash=str(getattr(ticket, "crop_hash", "") or ""),
        frame_seq=getattr(ticket, "frame_seq", None),
        prior_ticket_id=prior,
    )


def record_refuse(
    why: str,
    *,
    session_id: str = "",
    clock_ns: int | None = None,
    frame_seq: int | None = None,
    crop_hash: str = "",
) -> LookLicense | None:
    if not graph_enabled("ticket_provenance"):
        return None
    token = normalize_board_why(why)
    if token not in BOARD_WHY_UNLOCKED and token != "unlocked":
        return None
    if token in {"unlocked", "no_ticket", "confirm_ticket"}:
        return None
    return record_edge(
        "refuse",
        session_id=session_id,
        clock_ns=clock_ns,
        why=token,
        frame_seq=frame_seq,
        crop_hash=crop_hash,
    )


def next_confirm_look() -> LookLicense | None:
    """Code gate: what the next confirm look may do. Flag off → None (no-op)."""
    if not graph_enabled("ticket_provenance"):
        return None
    with _lock:
        last = _last_license
        blocked = _identity_blocked
        last_kind = _last_kind
        last_crop = _last_crop_hash
    if last is None:
        if blocked:
            return make_license(
                graph="ticket_provenance",
                kind="refuse",
                permits={"next_action": "refuse", "reuse_identity": False, "keep_crop": False},
                refuses=("identity_stale",),
            )
        return None
    if blocked or last_kind == "refuse":
        return make_license(
            graph="ticket_provenance",
            kind="refuse",
            session_id=last.session_id,
            clock_ns=last.clock_ns,
            permits={"next_action": "refuse", "reuse_identity": False, "keep_crop": False},
            refuses=tuple(last.refuses) + (("identity_stale",) if blocked else ()),
            source_ticket_id=last.source_ticket_id,
            frame_seq=last.frame_seq,
            crop_hash=last.crop_hash,
        )
    if last_kind == "reuse":
        return last
    if last_kind == "remint":
        return make_license(
            graph="ticket_provenance",
            kind="remint",
            session_id=last.session_id,
            clock_ns=last.clock_ns,
            permits={
                "next_action": "remint",
                "keep_crop": bool(last.crop_hash and last.crop_hash == last_crop),
                "reuse_identity": True,
            },
            source_ticket_id=last.source_ticket_id,
            frame_seq=last.frame_seq,
            crop_hash=last.crop_hash,
        )
    return last


def identity_blocked() -> bool:
    if not graph_enabled("ticket_provenance"):
        return False
    with _lock:
        return _identity_blocked


def last_edge() -> LookLicense | None:
    with _lock:
        return _last_license
