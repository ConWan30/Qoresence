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
    t_clock = int(sit_bag.get("confirm_clock_ns") or 0)
    l_clock = int(sit_bag.get("clock_ns") or sit_bag.get("live_clock_ns") or 0)
    ticket_id = str(sit_bag.get("confirm_ticket_id") or "") if has_ticket else ""
    ticket_crop = str(sit_bag.get("ticket_crop_hash") or "")
    live_crop = str(sit_bag.get("live_crop_hash") or sit_bag.get("crop_hash") or "")
    path = str(sit_bag.get("path") or "")
    try:
        from qoresence.monitor.frame_hub import get_latest_stamp
        from qoresence.vision.confirm_ticket import licensed_last_confirm

        last = licensed_last_confirm()
        stamp = get_latest_stamp() or {}
        if last is not None:
            ticket_id = str(last.ticket_id or ticket_id)
            t_clock = int(last.clock_ns or t_clock)
            ticket_crop = str(last.crop_hash or ticket_crop)
            locked = True
            has_ticket = True
        if stamp.get("clock_ns"):
            l_clock = int(stamp["clock_ns"])
        # Hub crop_hash is the full frame. ConfirmTicket.crop_hash is the
        # scorebug band — do not treat that mismatch as a moved HUD.
    except Exception:
        pass
    same = sit_bag.get("same_seq")
    abstain = str(sit_bag.get("vlm_status") or "").startswith("http_") or str(
        sit_bag.get("last_reason") or ""
    ) == "abstain"
    try:
        from qoresence.sync.digit_integrity import digit_void_reason, freshness_band

        reason = digit_void_reason(
            confirm_ticket_id=str(sit_bag.get("confirm_ticket_id") or ""),
            score_vlm_locked=locked,
            path=path,
            ticket_crop_hash=ticket_crop,
            live_crop_hash=live_crop,
            same_seq=same,
            ticket_clock_ns=t_clock,
            live_clock_ns=l_clock,
            vlm_abstain=abstain,
        )
        age = max(0, l_clock - t_clock) if t_clock and l_clock else 0
        out["digit_integrity"] = {"reason": reason, "band": freshness_band(age)}
    except Exception:
        pass
    try:
        from qoresence.sync.seqgate import license_digits, public_receipt

        out["seqgate"] = public_receipt(
            license_digits(
                confirm_ticket_id=ticket_id,
                score_vlm_locked=locked,
                path=path,
                ticket_crop_hash=ticket_crop,
                live_crop_hash=live_crop,
                same_seq=same if isinstance(same, bool) or same is None else bool(same),
                ticket_clock_ns=t_clock,
                live_clock_ns=l_clock,
                vlm_abstain=abstain,
                frame_seq=sit_bag.get("frame_seq"),
                home_score=sit_bag.get("home_score"),
                away_score=sit_bag.get("away_score"),
            )
        )
    except Exception:
        pass
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
