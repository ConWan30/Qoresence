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
    body["door"] = {
        "step": "export",
        "live_truth": "DARK",
        "copy": (
            "Eyes only. This envelope is an observation export — "
            "seal/wrap runs on QorTroller, not on Deck."
        ),
        "next": ["download envelope", "seal on QorTroller"],
        "chain": "paused",
    }
    return body
