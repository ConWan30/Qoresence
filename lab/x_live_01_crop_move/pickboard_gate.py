"""FIXTURE port of glass/src/lib/coupling/board.ts ticket-fresh / pickBoard.

Node 20 CI cannot --experimental-strip-types import board.ts. This port is
lab-only and must stay aligned with ticketFresh / digitsLicensed / pickBoard.
"""

from __future__ import annotations

import re
from typing import Any

CONFIRM_DIGIT_MAX_AGE_NS = 8_000_000_000


def _rec(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _num(v: Any, fallback: float = 0) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return fallback
    return n if n == n and n not in (float("inf"), float("-inf")) else fallback


def _int_or_null(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return int(n)


def _first_num(o: dict[str, Any], keys: list[str]) -> int | None:
    for k in keys:
        if o.get(k) is None or o.get(k) == "":
            continue
        n = _int_or_null(o.get(k))
        if n is not None:
            return n
    return None


def _first_str(o: dict[str, Any], keys: list[str]) -> str:
    for k in keys:
        v = o.get(k)
        if not isinstance(v, str):
            continue
        s = v.strip()
        if s and s not in ("true", "false"):
            return s
    return ""


def _first_bool(o: dict[str, Any], keys: list[str]) -> bool | None:
    for k in keys:
        v = o.get(k)
        if v is True or v is False:
            return v
        if v in (1, 0) and not isinstance(v, bool):
            return bool(v)
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("true", "yes", "on"):
                return True
            if s in ("false", "no", "off"):
                return False
    return None


def _parse_pair(raw: Any) -> tuple[int, int] | None:
    m = re.search(r"\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\b", str(raw or ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _crop_of(o: dict[str, Any]) -> str:
    return _first_str(o, ["crop_hash", "cropHash", "frame_hash", "frameHash"])


def _confirm_id_of(o: dict[str, Any]) -> str:
    return _first_str(o, ["ticket_id", "ticketId", "confirm_ticket_id", "confirmTicketId"])


def _score_pair_of(o: dict[str, Any]) -> tuple[int, int] | None:
    h = _first_num(o, ["home_score", "score_home", "homeScore"])
    a = _first_num(o, ["away_score", "score_away", "awayScore"])
    if h is not None and a is not None:
        return h, a
    return _parse_pair(o.get("score") or o.get("scoreline") or o.get("board"))


def ticket_fresh(
    *,
    ticket_crop_hash: str,
    live_crop_hash: str = "",
    same_seq: bool | None = None,
    ticket_clock_ns: float = 0,
    live_clock_ns: float = 0,
    max_age_ns: int = CONFIRM_DIGIT_MAX_AGE_NS,
) -> bool:
    ticket_crop = str(ticket_crop_hash or "").strip()
    if not ticket_crop:
        return False
    live_crop = str(live_crop_hash or "").strip()
    if live_crop and live_crop != ticket_crop:
        return False
    if same_seq is False:
        return False
    t_clock = _num(ticket_clock_ns, 0)
    l_clock = _num(live_clock_ns, 0)
    if t_clock > 0 and l_clock > 0 and l_clock - t_clock > max_age_ns:
        return False
    return True


def digits_licensed(
    *,
    confirm_ticket_id: str,
    score_vlm_locked: bool,
    ticket_crop_hash: str,
    live_crop_hash: str = "",
    same_seq: bool | None = None,
    ticket_clock_ns: float = 0,
    live_clock_ns: float = 0,
) -> bool:
    if not str(confirm_ticket_id or "").strip():
        return False
    if not score_vlm_locked:
        return False
    return ticket_fresh(
        ticket_crop_hash=ticket_crop_hash,
        live_crop_hash=live_crop_hash,
        same_seq=same_seq,
        ticket_clock_ns=ticket_clock_ns,
        live_clock_ns=live_clock_ns,
    )


def pick_board(*bags: dict[str, Any]) -> dict[str, Any]:
    cand_home: int | None = None
    cand_away: int | None = None
    confirm_ticket_id = ""
    score_vlm_locked = False
    ticket_crop = ""
    live_crop = ""
    same_seq: bool | None = None
    ticket_clock_ns = 0.0
    live_clock_ns = 0.0

    def take_candidate(o: dict[str, Any], prefer: bool = False) -> None:
        nonlocal cand_home, cand_away
        pair = _score_pair_of(o)
        if not pair:
            return
        if prefer or cand_home is None:
            cand_home, cand_away = pair

    def take_ticket(o: dict[str, Any]) -> None:
        nonlocal confirm_ticket_id, ticket_crop, ticket_clock_ns, score_vlm_locked
        if not o:
            return
        tid = _confirm_id_of(o)
        if tid and not confirm_ticket_id:
            confirm_ticket_id = tid
        crop = _crop_of(o)
        if crop and not ticket_crop:
            ticket_crop = crop
        clk = _num(o.get("clock_ns", o.get("clockNs")), 0)
        if clk and not ticket_clock_ns:
            ticket_clock_ns = clk
        if _first_bool(o, ["score_vlm_locked", "scoreVlmLocked"]) is True:
            score_vlm_locked = True
        take_candidate(o, True)

    def take_live(o: dict[str, Any]) -> None:
        nonlocal score_vlm_locked, confirm_ticket_id, live_crop, same_seq, live_clock_ns
        if not o:
            return
        if _first_bool(o, ["score_vlm_locked", "scoreVlmLocked"]) is True:
            score_vlm_locked = True
        tid = _first_str(o, ["confirm_ticket_id", "confirmTicketId"])
        if tid and not confirm_ticket_id:
            confirm_ticket_id = tid
        crop = _crop_of(o)
        if crop:
            live_crop = crop
        if o.get("same_seq") is not None or o.get("sameSeq") is not None:
            same_seq = bool(o.get("same_seq", o.get("sameSeq")))
        clk = _num(o.get("clock_ns", o.get("clockNs", o.get("updated_ns", o.get("updatedNs")))), 0)
        if clk:
            live_clock_ns = clk
        take_candidate(o, False)

    for bag in bags:
        confirm = _rec(bag.get("confirm"))
        take_ticket(_rec(confirm.get("last_confirm")))
        take_ticket(_rec(bag.get("last_confirm")))
        take_live(bag)
        take_live(_rec(bag.get("situation")))
        take_live(_rec(bag.get("payload")))
        take_live(_rec(bag.get("visual_context")))
        take_live(_rec(bag.get("scoreboard")))
        take_live(_rec(bag.get("video")))
        take_live(_rec(confirm.get("last_fast")))
        take_live(_rec(bag.get("last_fast")))

    if confirm_ticket_id and not ticket_crop and live_crop:
        ticket_crop = live_crop

    locked = digits_licensed(
        confirm_ticket_id=confirm_ticket_id,
        score_vlm_locked=score_vlm_locked,
        ticket_crop_hash=ticket_crop,
        live_crop_hash=live_crop,
        same_seq=same_seq,
        ticket_clock_ns=ticket_clock_ns,
        live_clock_ns=live_clock_ns,
    )
    return {
        "home": cand_home if locked else None,
        "away": cand_away if locked else None,
        "locked": locked,
    }


def scorebug_pair(home: int | None, away: int | None) -> str:
    if home is None or away is None:
        return ""
    return f"{home}-{away}"
