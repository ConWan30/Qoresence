"""Map Session Theater view/recap packs onto an observation envelope."""

from __future__ import annotations

from typing import Any

from .envelope import ObservationEnvelope, envelope_from_recap
from .io_ledger import out_edge_from_event
from .locks import compose_locks
from .sanitize import strip_truth_leaks


def _truthy_fresh(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _confirm_ticket_id(raw: dict[str, Any], ev: dict[str, Any]) -> str:
    for src in (ev, raw):
        tid = str(src.get("confirm_ticket_id") or "").strip()
        if tid:
            return tid
    if str(ev.get("ticket_kind") or "").strip() == "confirm":
        return str(ev.get("ticket_id") or ev.get("event_id") or "").strip()
    return ""


def _score_vlm_locked(raw: dict[str, Any], ev: dict[str, Any]) -> bool:
    if "score_vlm_locked" in ev:
        return bool(ev.get("score_vlm_locked"))
    if "score_vlm_locked" in raw:
        return bool(raw.get("score_vlm_locked"))
    return False


def _ticket_fresh_ok(raw: dict[str, Any], ev: dict[str, Any]) -> bool:
    if "ticket_fresh" in ev:
        return _truthy_fresh(ev.get("ticket_fresh"))
    if "ticket_fresh" in raw:
        return _truthy_fresh(raw.get("ticket_fresh"))
    return True


def _digits_licensed(raw: dict[str, Any], ev: dict[str, Any]) -> bool:
    if not _score_vlm_locked(raw, ev):
        return False
    if not _confirm_ticket_id(raw, ev):
        return False
    return _ticket_fresh_ok(raw, ev)


def _format_digits(score_obj: Any) -> str | None:
    if not isinstance(score_obj, dict):
        return None
    if score_obj.get("home") is None or score_obj.get("away") is None:
        return None
    return f"{int(score_obj['home'])}-{int(score_obj['away'])}"


def recap_from_session_view(view: dict[str, Any] | None) -> dict[str, Any]:
    raw = strip_truth_leaks(view if isinstance(view, dict) else {})
    locked = bool(raw.get("board_locked"))
    bodied = bool(raw.get("controller_bodied"))
    ticks: list[dict[str, Any]] = []
    for ev in raw.get("events") or []:
        if not isinstance(ev, dict):
            continue
        licensed = _digits_licensed(raw, ev)
        digits = _format_digits(ev.get("score")) if licensed else None
        hid = None
        inp = ev.get("input") if isinstance(ev.get("input"), dict) else {}
        if bodied:
            hid = inp.get("button") or inp.get("hid_edge")
        ticket = (
            str(ev.get("confirm_ticket_id") or "").strip()
            or str(ev.get("event_id") or ev.get("ticket_id") or "").strip()
            or None
        )
        kind = None
        if licensed:
            kind = "confirm"
        elif ticket or hid or inp:
            kind = "coupling"
        tick = {
            "clock_ns": int(ev.get("t_start_ns") or ev.get("clock_ns") or 0),
            "frame_seq": int(ev.get("frame_seq") or ev.get("seq") or 0),
            "ticket_id": ticket,
            "ticket_kind": kind,
            "hid_edge": hid,
            "score_digits": digits,
            "score_vlm_locked": bool(licensed),
        }
        out_edge = out_edge_from_event(ev)
        if out_edge is not None:
            tick["out_edge"] = out_edge
        ticks.append(tick)
    return {
        "schema": "qoresence.session-recap-1",
        "session_id": str(raw.get("session_id") or ""),
        "hid_on_console": not bodied,
        "board_locked": locked,
        "ticks": ticks,
        "buttons_sha256": raw.get("buttons_sha256"),
        "coupling_sha256": raw.get("coupling_sha256"),
    }


def envelope_from_session_view(view: dict[str, Any] | None) -> ObservationEnvelope:
    recap = recap_from_session_view(view)
    if not recap.get("session_id"):
        recap["session_id"] = "session-unknown"
    return envelope_from_recap(recap)


def payload_from_session_view(view: dict[str, Any] | None) -> dict[str, Any]:
    recap = recap_from_session_view(view)
    if not recap.get("session_id"):
        return {
            "ok": False,
            "plane": "observation",
            "error": "no_session",
            "locks": compose_locks(
                coupling_ticket=False, same_seq=False, consent_granted=False, wrap_sealed=False
            ).to_hud(),
        }
    env = envelope_from_recap(recap)
    coupling = any(t.get("ticket_kind") == "coupling" and t.get("ticket_id") for t in env.ticks)
    locks = compose_locks(
        coupling_ticket=coupling,
        same_seq=True,
        consent_granted=False,
        wrap_sealed=False,
    )
    body = env.to_dict()
    body["ok"] = True
    body["locks"] = locks.to_hud()
    body["notary"] = {
        "status": "UNSEALED",
        "reason": "observation plane cannot wrap — hand envelope to QorTroller after gamer consent",
    }
    return body
