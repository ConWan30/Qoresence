"""Refuse-reason causal chain — after a refuse, what the next look may try.

Maps board_why / FREEZE kinds onto existing constraint kinds only.
No new speech on the gamer Now strip.
"""

from __future__ import annotations

import threading
from typing import Any

from qoresence.graphs.flags import graph_enabled, note_applied
from qoresence.graphs.look_license import LookLicense, append_license, make_license
from qoresence.pilot.metrics import FREEZE_KINDS
from qoresence.vision.board_why import BOARD_WHY_UNLOCKED, normalize_board_why

# Causal successors after a refuse / freeze token.
_CHAIN: dict[str, tuple[str, ...]] = {
    "identity_swap": ("refuse_identity_swap", "identity_stale", "mint_blocked"),
    "refuse_identity_swap": ("identity_stale", "mint_blocked"),
    "zero_zero_after_identity_swap": ("refuse_zero_zero", "identity_stale", "mint_blocked"),
    "zero_zero_after_nonzero": ("refuse_zero_zero", "identity_stale", "mint_blocked"),
    "refuse_zero_zero": ("identity_stale", "mint_blocked"),
    "refuse_suspicious": ("schedule_skip",),
    "suspicious_pair": ("schedule_skip",),
    "vlm_quota": ("schedule_skip",),
    "vlm_auth": ("schedule_skip",),
    "vlm_no_key": ("schedule_skip",),
    "menu": ("pause_crops_only",),
    "loading": ("pause_crops_only",),
    "card_stall": ("freeze_weight",),
    "graph_stall": ("freeze_weight",),
    "deck_lock": ("freeze_weight",),
    "unknown": ("freeze_weight",),
}

_lock = threading.Lock()
_last_license: LookLicense | None = None
_mint_blocked: bool = False
_pause_crops: bool = False
_skip_unit: str = ""


def reset() -> None:
    global _last_license, _mint_blocked, _pause_crops, _skip_unit
    with _lock:
        _last_license = None
        _mint_blocked = False
        _pause_crops = False
        _skip_unit = ""


def apply_refuse(
    token: str,
    *,
    freeze_kind: str | None = None,
    session_id: str = "",
    clock_ns: int | None = None,
    ticket_id: str = "",
    frame_seq: int | None = None,
) -> LookLicense | None:
    global _last_license, _mint_blocked, _pause_crops, _skip_unit
    if not graph_enabled("refuse_chain"):
        return None
    raw = str(token or "").strip()
    why = normalize_board_why(raw, default="")
    key = why if why and why != "unlocked" else raw
    if freeze_kind and str(freeze_kind) in FREEZE_KINDS:
        key = str(freeze_kind)
    successors = _CHAIN.get(key) or _CHAIN.get(raw)
    if not successors:
        if raw in BOARD_WHY_UNLOCKED:
            successors = ()
        else:
            return None

    kind = "refuse"
    permits: dict[str, Any] = {"next_action": "refuse", "reuse_identity": True}
    if "mint_blocked" in successors:
        kind = "mint_blocked"
        permits["next_action"] = "refuse"
        permits["reuse_identity"] = False
    if "schedule_skip" in successors:
        kind = "schedule_skip"
        permits["next_action"] = "skip"
        permits["constraint_kind"] = "schedule_skip"
        permits["unit_kind"] = "confirm"
    if "pause_crops_only" in successors:
        kind = "pause_crops_only"
        permits["next_action"] = "crop"
        permits["crop_role"] = "pause"
    if "freeze_weight" in successors:
        kind = "schedule_skip"
        permits["constraint_kind"] = "freeze_weight"
        permits["freeze_kind"] = key if key in FREEZE_KINDS else "unknown"
        permits["weight"] = 1.0
        permits["next_action"] = "skip"

    lic = make_license(
        graph="refuse_chain",
        kind=kind,
        session_id=session_id,
        clock_ns=clock_ns,
        permits=permits,
        refuses=successors,
        source_ticket_id=ticket_id,
        frame_seq=frame_seq,
    )
    if lic is None:
        return None

    with _lock:
        _last_license = lic
        if "mint_blocked" in successors:
            _mint_blocked = True
        if "pause_crops_only" in successors:
            _pause_crops = True
        if "schedule_skip" in successors:
            _skip_unit = "confirm"
    append_license(lic)
    note_applied(lic.id)
    _maybe_learning_constraint(lic)
    if "mint_blocked" in successors:
        try:
            from qoresence.graphs.ticket_provenance import note_identity_stale

            note_identity_stale()
        except Exception:
            pass
    if "pause_crops_only" in successors:
        try:
            from qoresence.graphs.crop_evidence import record_pause_menu

            record_pause_menu(None, clock_ns=clock_ns, session_id=session_id)
        except Exception:
            pass
    return lic


def mint_blocked() -> bool:
    if not graph_enabled("refuse_chain"):
        return False
    with _lock:
        return _mint_blocked


def pause_crops_only() -> bool:
    if not graph_enabled("refuse_chain"):
        return False
    with _lock:
        return _pause_crops


def schedule_skip_unit() -> str:
    if not graph_enabled("refuse_chain"):
        return ""
    with _lock:
        return _skip_unit


def last_license() -> LookLicense | None:
    with _lock:
        return _last_license


def clear_mint_block() -> None:
    global _mint_blocked
    with _lock:
        _mint_blocked = False


def _maybe_learning_constraint(lic: LookLicense) -> None:
    """When both flags are on and a seeing-path ticket exists, write an existing kind."""
    try:
        import os

        from qoresence.agents.learning_constraint import DEFAULT_CONSTRAINT_LOG, append_constraint
        from qoresence.graphs.look_license import maybe_constraint_from_license
        from qoresence.vision.confirm_ticket import get_ticket_book

        ticket = get_ticket_book().latest()
        constraint = maybe_constraint_from_license(lic, ticket=ticket)
        if constraint is None:
            return
        envp = os.environ.get("QORESENCE_LEARNING_CONSTRAINTS_PATH", "").strip()
        append_constraint(constraint, path=envp or DEFAULT_CONSTRAINT_LOG)
    except Exception:
        pass
