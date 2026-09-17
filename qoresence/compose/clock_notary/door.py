"""Gamer-facing observation export door. Seal/wrap lives on QorTroller, not Deck."""

from __future__ import annotations

from typing import Any

from .from_session import payload_from_session_view


def _as_view(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    if isinstance(raw.get("view"), dict):
        return raw["view"]
    return raw


def export_door(session_view: dict[str, Any] | None) -> dict[str, Any]:
    """Observation export for Recap. Eyes only — Truth seal is QorTroller."""
    view = _as_view(session_view)
    body = payload_from_session_view(view)
    hygiene = None
    try:
        from qoresence.observability.recap_hygiene import inspect_envelope

        hygiene = inspect_envelope(body)
    except Exception:
        hygiene = None
    hold = bool(hygiene and hygiene.get("hold"))
    body["door"] = {
        "step": "export",
        "live_truth": "DARK",
        "copy": (
            "Would rather go blank than keep a stale score. "
            "Eyes only — seal/wrap runs on QorTroller, not on Deck."
            if hold
            else (
                "Eyes only. This envelope is an observation export — "
                "seal/wrap runs on QorTroller, not on Deck."
            )
        ),
        "next": ["download envelope", "seal on QorTroller"],
        "chain": "paused",
        "hygiene": (
            {
                "ok": hygiene.get("ok"),
                "hold": hygiene.get("hold"),
                "reason": hygiene.get("reason"),
                "issue_kind": hygiene.get("issue_kind"),
                "citation": hygiene.get("citation"),
                "seals": False,
                "licenses_digits": False,
            }
            if hygiene
            else None
        ),
    }
    if hold:
        # Fail closed: do not hand a leaky envelope to siblings.
        body["ok"] = False
        body["ticks"] = []
        body["clock_commitment"] = ""
        body["notary"] = {
            "status": "HOLD",
            "reason": str(hygiene.get("reason") or "hygiene_hold"),
        }
    return body
