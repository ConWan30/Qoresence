"""Map Session Theater view/recap packs onto an observation envelope."""

from __future__ import annotations

from typing import Any

from .envelope import ObservationEnvelope, envelope_from_recap
from .locks import compose_locks
from .sanitize import strip_truth_leaks


def recap_from_session_view(view: dict[str, Any] | None) -> dict[str, Any]:
    raw = strip_truth_leaks(view if isinstance(view, dict) else {})
    locked = bool(raw.get("board_locked"))
    bodied = bool(raw.get("controller_bodied"))
    ticks: list[dict[str, Any]] = []
    for ev in raw.get("events") or []:
        if not isinstance(ev, dict):
            continue
        score_obj = ev.get("score") if locked else None
        digits = None
        if isinstance(score_obj, dict) and score_obj.get("home") is not None and score_obj.get("away") is not None:
            digits = f"{int(score_obj['home'])}-{int(score_obj['away'])}"
        hid = None
        inp = ev.get("input") if isinstance(ev.get("input"), dict) else {}
        if bodied:
            hid = inp.get("button") or inp.get("hid_edge")
        ev_locked = bool(digits)
        kind = None
        ticket = ev.get("event_id") or ev.get("ticket_id")
        if ev_locked:
            kind = "confirm"
        elif ticket or hid or inp:
            kind = "coupling"
        ticks.append(
            {
                "clock_ns": int(ev.get("t_start_ns") or ev.get("clock_ns") or 0),
                "frame_seq": int(ev.get("frame_seq") or ev.get("seq") or 0),
                "ticket_id": ticket,
                "ticket_kind": kind,
                "hid_edge": hid,
                "score_digits": digits,
                "score_vlm_locked": ev_locked,
            }
        )
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
