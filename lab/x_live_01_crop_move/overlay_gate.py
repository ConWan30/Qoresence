"""Mirror of qoresence/deck/overlay.html digitsLicensed — FIXTURE only."""

from __future__ import annotations

from typing import Any


def overlay_digits_licensed(situation: dict[str, Any], snap: dict[str, Any] | None) -> bool:
    """Same claim ceiling as overlay.html — ConfirmTicket + VLM lock + crop match."""
    confirm = (snap or {}).get("confirm") if isinstance(snap, dict) else {}
    last = {}
    if isinstance(confirm, dict):
        raw = confirm.get("last_confirm")
        last = raw if isinstance(raw, dict) else {}
    if not last:
        raw = situation.get("last_confirm")
        last = raw if isinstance(raw, dict) else {}
    tid = str(last.get("ticket_id") or situation.get("confirm_ticket_id") or "").strip()
    vlm = situation.get("score_vlm_locked") is True or last.get("score_vlm_locked") is True
    if not tid or not vlm:
        return False
    ticket_crop = str(last.get("crop_hash") or "").strip()
    live_crop = str(situation.get("crop_hash") or situation.get("frame_hash") or "").strip()
    crop = ticket_crop or live_crop
    if not crop:
        return False
    if ticket_crop and live_crop and ticket_crop != live_crop:
        return False
    video = (snap or {}).get("video") if isinstance(snap, dict) else {}
    if isinstance(video, dict) and video.get("same_seq") is False:
        return False
    return True


def overlay_score_text(situation: dict[str, Any], snap: dict[str, Any] | None) -> str:
    """overlay.html score fragment — empty string when the gate vetoes."""
    if not overlay_digits_licensed(situation, snap):
        return ""
    if situation.get("score_home") is not None:
        return f"{situation.get('score_home')}-{situation.get('score_away')}"
    if situation.get("home_score") is not None:
        return f"{situation.get('home_score')}-{situation.get('away_score')}"
    if situation.get("score") is not None:
        return str(situation.get("score"))
    return ""
