"""Attach seeing-path speech to Deck /health snapshots.

Observation only. Does not emit bus events. Does not leak confirm ticket ids.
"""

from __future__ import annotations

from typing import Any

_PATCHED = False


def attach_board_health(out: dict[str, Any], situation: Any) -> dict[str, Any]:
    sit_bag = situation if isinstance(situation, dict) else {}
    out["board_why"] = str(sit_bag.get("board_why") or "")
    locked = bool(sit_bag.get("score_vlm_locked"))
    has_ticket = bool(str(sit_bag.get("confirm_ticket_id") or "").strip())
    try:
        from qoresence.vision.confirm_ticket import confirm_glass_must_blank

        if confirm_glass_must_blank():
            locked = False
            has_ticket = False
    except Exception:
        pass
    out["score_vlm_locked"] = locked
    out["has_confirm_ticket"] = has_ticket
    try:
        from qoresence.graphs.look_gate import snapshot as look_snapshot

        look = look_snapshot()
        if look is not None:
            out["look_scale"] = str(look.get("scale") or "")
            out["look_join"] = str(look.get("join") or "")
            out["look_permit_confirm"] = bool(look.get("permit_confirm"))
            out["look_refuse"] = str(look.get("refuse") or "")
    except Exception:
        pass
    return out


def install_health_patch() -> None:
    """Wrap DeckState._snapshot_fresh so /health exposes board_why."""
    global _PATCHED
    if _PATCHED:
        return
    from qoresence.deck.server import DeckState

    orig = DeckState._snapshot_fresh
    if getattr(orig, "_board_why_patched", False):
        _PATCHED = True
        return

    def wrapped(self: Any) -> dict[str, Any]:
        out = orig(self)
        return attach_board_health(out, getattr(self, "situation", {}))

    wrapped._board_why_patched = True  # type: ignore[attr-defined]
    DeckState._snapshot_fresh = wrapped  # type: ignore[method-assign]
    _PATCHED = True
