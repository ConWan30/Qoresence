"""Look gate — enforce LookLicense on the live seeing path.

Flag off → every permit is True (identical to main). Never emits bus events.
Never takes a lobe lock. Query-only on the hot path (no JSONL).
"""

from __future__ import annotations

from typing import Any

from qoresence.graphs.flags import enabled, graph_enabled


def permit_confirm_look(
    *,
    reason: str = "tick",
    force: bool = False,
    has_frame: bool = True,
    blank: bool = False,
) -> bool:
    """May confirm-path VLM HTTP run? Flag off → True.

    Tick HTTP is allowed whenever has_frame and not blank — same as flag-off
    for the seeing-path. scale_tick / no active_drive HOLDs mint/speech via
    permit_confirm_mint, never skips Quicksilver. Same-Seq seq_skew /
    plane_dim, refuse-chain schedule_skip, blank, and no_frame still refuse.
    ``reason`` / ``force`` are kept for callers; they do not gate HTTP.
    """
    if not enabled():
        return True
    if blank or not has_frame:
        return False
    if graph_enabled("same_seq_join"):
        try:
            from qoresence.graphs.same_seq_join import confirm_look_allowed

            if not confirm_look_allowed():
                return False
        except Exception:
            pass
    if graph_enabled("refuse_chain"):
        try:
            from qoresence.graphs.refuse_chain import schedule_skip_unit

            if schedule_skip_unit() == "confirm":
                return False
        except Exception:
            pass
    return True


def permit_ocr_look() -> bool:
    """May EasyOCR / Paddle run this tick? Flag off → True. Peek is tick-legal."""
    if not enabled():
        return True
    if graph_enabled("same_seq_join"):
        try:
            from qoresence.graphs.same_seq_join import confirm_look_allowed

            if not confirm_look_allowed():
                return False
        except Exception:
            pass
    return True


def permit_confirm_mint(*, reuse: bool) -> bool:
    """May put/reuse a confirm ticket? Flag off → True.

    Reuse of the last identity is refused while provenance/refuse-chain
    mark identity stale. A remint (new scores or sides) is allowed.
    scale_tick / no active_drive never skip VLM HTTP (see permit_confirm_look);
    they may still HOLD reuse mint/speech through refuse-chain / identity.
    """
    if not enabled():
        return True
    if not reuse:
        return True
    if graph_enabled("ticket_provenance"):
        try:
            from qoresence.graphs.ticket_provenance import identity_blocked

            if identity_blocked():
                return False
        except Exception:
            pass
    if graph_enabled("refuse_chain"):
        try:
            from qoresence.graphs.refuse_chain import mint_blocked

            if mint_blocked():
                return False
        except Exception:
            pass
    if graph_enabled("scale_stack"):
        try:
            if not _active_drive():
                return False
        except Exception:
            pass
    return True


def mint_hold_drops_lock() -> bool:
    """True when a mint HOLD must drop score_vlm_locked.

    Identity / refuse-chain HOLD unlicenses. scale_tick HOLD keeps a
    previously licensed ticket so digits do not starve after the first mint.
    """
    if not enabled():
        return False
    if graph_enabled("ticket_provenance"):
        try:
            from qoresence.graphs.ticket_provenance import identity_blocked

            if identity_blocked():
                return True
        except Exception:
            pass
    if graph_enabled("refuse_chain"):
        try:
            from qoresence.graphs.refuse_chain import mint_blocked

            if mint_blocked():
                return True
        except Exception:
            pass
    return False


def _active_drive() -> bool:
    try:
        from qoresence.agents.session_timeline import get_session_timeline

        return get_session_timeline().active_drive() is not None
    except Exception:
        return False


def snapshot() -> dict[str, Any] | None:
    """Operator glass for /health. None when flag off. No ticket ids. No JSONL."""
    if not enabled():
        return None
    join = ""
    scale = ""
    skip = ""
    try:
        from qoresence.graphs.same_seq_join import last_license

        lic = last_license()
        if lic is not None:
            join = str(lic.kind or "")
    except Exception:
        pass
    try:
        from qoresence.graphs.scale_stack import licensed_scale

        scale = str(licensed_scale() or "")
    except Exception:
        pass
    try:
        from qoresence.graphs.refuse_chain import schedule_skip_unit

        skip = str(schedule_skip_unit() or "")
    except Exception:
        pass
    reasons: list[str] = []
    if skip == "confirm":
        reasons.append("schedule_skip")
    if join in {"seq_skew", "plane_dim"}:
        reasons.append(join)
    # scale_tick is mint/speech HOLD, not a seeing-path HTTP skip.
    return {
        "scale": scale or "tick",
        "join": join,
        "permit_confirm": not reasons,
        "refuse": ",".join(reasons),
    }
