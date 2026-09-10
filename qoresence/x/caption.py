"""Fail-closed X Glass caption builder.

Digits only with ConfirmTicket + score_vlm_locked + ticket-fresh crop_hash.
board_locked / scoreboard_locked alone NEVER license digits.
Blank beats hold. No URL in caption. One video per post (path separate).
"""

from __future__ import annotations

from typing import Any

from qoresence.sync.digit_integrity import digit_void_reason

PLANE = "qoresence-observation"


def _rec(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _str(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _bool(v: Any) -> bool:
    return v is True or v == 1 or (isinstance(v, str) and v.strip().lower() in ("1", "true", "yes"))


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def extract_digit_gate(situation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pull ConfirmTicket / VLM lock / crop freshness from a situation bag.

    Intentionally ignores board_locked / scoreboard_locked / widgetsOk.
    """
    sit = _rec(situation)
    confirm = _rec(sit.get("confirm"))
    last_confirm = _rec(confirm.get("last_confirm") or sit.get("last_confirm"))
    video = _rec(sit.get("video"))

    ticket_id = _str(
        sit.get("confirm_ticket_id")
        or last_confirm.get("ticket_id")
        or last_confirm.get("confirm_ticket_id")
        or confirm.get("ticket_id")
    )
    score_vlm_locked = _bool(
        sit.get("score_vlm_locked")
        or last_confirm.get("score_vlm_locked")
        or confirm.get("score_vlm_locked")
    )
    # board_locked alone is NOT permission — read but never use as license.
    _ = _bool(sit.get("board_locked") or sit.get("scoreboard_locked"))

    ticket_crop = _str(
        sit.get("ticket_crop_hash")
        or last_confirm.get("crop_hash")
        or confirm.get("crop_hash")
    )
    live_crop = _str(video.get("crop_hash") or sit.get("crop_hash") or "")
    same_seq = sit.get("same_seq")
    if same_seq is not None and not isinstance(same_seq, bool):
        same_seq = bool(same_seq)
    ticket_clock = _int(sit.get("confirm_clock_ns") or last_confirm.get("clock_ns"))
    live_clock = _int(sit.get("updated_ns") or sit.get("clock_ns") or video.get("clock_ns"))
    home = sit.get("home_score", last_confirm.get("home_score"))
    away = sit.get("away_score", last_confirm.get("away_score"))
    title = _str(sit.get("title") or sit.get("title_presence") or sit.get("game_title"))

    reason = digit_void_reason(
        confirm_ticket_id=ticket_id,
        score_vlm_locked=score_vlm_locked,
        path="confirm",
        ticket_crop_hash=ticket_crop,
        live_crop_hash=live_crop or ticket_crop,
        same_seq=same_seq,
        ticket_clock_ns=ticket_clock,
        live_clock_ns=live_clock,
    )
    licensed = reason == "licensed"
    return {
        "confirm_ticket_id": ticket_id,
        "score_vlm_locked": score_vlm_locked,
        "ticket_crop_hash": ticket_crop,
        "live_crop_hash": live_crop,
        "licensed": licensed,
        "void_reason": reason,
        "home_score": home,
        "away_score": away,
        "title": title,
        "digit_silent": not licensed,
    }


def build_caption(
    situation: dict[str, Any] | None = None,
    *,
    caption_mode: str = "auto",
) -> dict[str, Any]:
    """Server-side caption. No free-text. No URL. Digits fail-closed.

    caption_mode:
      - auto: score line only when ConfirmTicket+score_vlm_locked+ticket-fresh
      - silent: never emit digits (always digit_silent)
    """
    mode = str(caption_mode or "auto").strip().lower()
    if mode not in ("auto", "silent"):
        mode = "auto"

    gate = extract_digit_gate(situation)
    title = gate["title"]
    lines: list[str] = []
    if title:
        # Title presence only — never a URL, never invented digits.
        lines.append(title)

    digit_silent = True
    score_line = ""
    if mode == "silent":
        digit_silent = True
    elif gate["licensed"]:
        home, away = gate["home_score"], gate["away_score"]
        if home is not None and away is not None:
            score_line = f"{home}-{away}"
            lines.append(score_line)
            digit_silent = False
        else:
            digit_silent = True
    else:
        digit_silent = True

    caption = "\n".join(lines).strip()
    # Hard: never embed URLs
    if "http://" in caption.lower() or "https://" in caption.lower() or "x.com/" in caption.lower():
        caption = "\n".join(ln for ln in lines if "http" not in ln.lower() and "x.com/" not in ln.lower()).strip()

    return {
        "caption": caption,
        "score_line": score_line,
        "digit_silent": digit_silent,
        "caption_mode": mode,
        "gate": gate,
        "plane": PLANE,
    }
