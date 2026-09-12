"""SEQGATE v0 — Sequence Gate Harness. Same frame or silence.

Fail-closed frame-license for digit/claim speech. Wraps Null Digit +
ticket-fresh + capture lease. Never last-good freeze. Ident Latch (#145) is HOLD.
"""

from __future__ import annotations

from typing import Any

from qoresence.sync.digit_integrity import digit_void_reason

SLOGAN = "Same frame or silence."
PLANE = "qoresence-observation"
NULL_DIGIT = "□–□"
HOLD = "HOLD"
FRESH_BUDGET_NS = 8_000_000_000

KINDS = frozenset({"fact", "ticket", "veto", "hold"})
PATHS = frozenset({"fast", "confirm"})

_SCORE_KEYS = ("home_score", "away_score", "score_home", "score_away", "score")

_REASON_LAYER = {
    "path_fast": "ticket",
    "no_ticket": "ticket",
    "vlm_unlocked": "ticket",
    "ticket_stale": "fresh",
    "crop_mismatch": "fresh",
    "seq_skew": "same_seq",
    "vlm_abstain": "abstain",
    "licensed": "ticket",
    "vocab_veto": "vocab",
}

_VOCAB_BANNED = (
    "authorship",
    "eligibility",
    "humanity",
    "anti-cheat",
    "anticheat",
    "you threw that",
    "threw that",
    "proof of human",
    "lag switch",
)


def bind(
    *,
    clock_ns: int = 0,
    frame_seq: int | None = None,
    path: str = "confirm",
    kind: str = "hold",
) -> dict[str, Any]:
    p = str(path or "confirm").lower()
    if p not in PATHS:
        p = "confirm"
    k = str(kind or "hold").lower()
    if k not in KINDS:
        k = "hold"
    seq: int | None
    try:
        seq = int(frame_seq) if frame_seq is not None else None
    except (TypeError, ValueError):
        seq = None
    return {
        "clock_ns": int(clock_ns or 0),
        "frame_seq": seq,
        "path": p,
        "plane": PLANE,
        "kind": k,
    }


def vocab_veto(text: str) -> str | None:
    blob = str(text or "").lower()
    if not blob.strip():
        return None
    for term in _VOCAB_BANNED:
        if term in blob:
            return "vocab_veto"
    return None


def _kind_for(reason: str, path: str) -> str:
    if reason == "licensed":
        return "fact"
    if reason in {"path_fast", "vocab_veto"}:
        return "veto"
    return "hold"


def _speech(home: Any, away: Any, licensed: bool) -> str:
    if not licensed:
        return NULL_DIGIT
    if home is None or away is None:
        return NULL_DIGIT
    return f"{home}-{away}"


def license_digits(
    *,
    confirm_ticket_id: str = "",
    score_vlm_locked: bool = False,
    path: str = "",
    ticket_crop_hash: str = "",
    live_crop_hash: str = "",
    same_seq: bool | None = None,
    ticket_clock_ns: int = 0,
    live_clock_ns: int = 0,
    vlm_abstain: bool = False,
    frame_seq: int | None = None,
    home_score: Any = None,
    away_score: Any = None,
) -> dict[str, Any]:
    """License hard digits. Missing ticket/lock/fresh → □–□. Never last-good."""
    p = str(path or "").lower() or "confirm"
    reason = digit_void_reason(
        confirm_ticket_id=confirm_ticket_id,
        score_vlm_locked=score_vlm_locked,
        path=p,
        ticket_crop_hash=ticket_crop_hash,
        live_crop_hash=live_crop_hash,
        same_seq=same_seq,
        ticket_clock_ns=ticket_clock_ns,
        live_clock_ns=live_clock_ns,
        vlm_abstain=vlm_abstain,
    )
    licensed = reason == "licensed"
    kind = _kind_for(reason, p)
    return {
        "licensed": licensed,
        "reason": reason,
        "speech": _speech(home_score, away_score, licensed),
        "layer": _REASON_LAYER.get(reason, "abstain"),
        "bind": bind(
            clock_ns=live_clock_ns,
            frame_seq=frame_seq,
            path="fast" if p == "fast" else "confirm",
            kind=kind,
        ),
    }


def license_claim(text: str, **digit_kwargs: Any) -> dict[str, Any]:
    """Vocab veto then digit license. Banned talk → HOLD, not a claim."""
    if vocab_veto(text) is not None:
        p = str(digit_kwargs.get("path") or "confirm").lower()
        return {
            "licensed": False,
            "reason": "vocab_veto",
            "speech": HOLD,
            "layer": "vocab",
            "bind": bind(
                clock_ns=int(digit_kwargs.get("live_clock_ns") or 0),
                frame_seq=digit_kwargs.get("frame_seq"),
                path="fast" if p == "fast" else "confirm",
                kind="veto",
            ),
        }
    return license_digits(**digit_kwargs)


def lease_layer(
    device: str = "USB3.0 Video",
    lock_dir: Any = None,
) -> dict[str, Any]:
    """Named exclusive capture lease — existing module, not a second lock."""
    from qoresence.capture.lease import lease_health

    h = lease_health(lock_dir=lock_dir, device=device)
    return {
        "layer": "lease",
        "ok": bool(h.get("ok")),
        "owner": str(h.get("owner") or ""),
        "pid": int(h.get("pid") or 0),
        "device": str(h.get("device") or device),
    }


def public_receipt(gate: dict[str, Any]) -> dict[str, Any]:
    """Operator/agent receipt. No ticket ids."""
    bind_st = gate.get("bind") if isinstance(gate.get("bind"), dict) else {}
    return {
        "licensed": bool(gate.get("licensed")),
        "reason": str(gate.get("reason") or "hold"),
        "speech": str(gate.get("speech") or NULL_DIGIT),
        "layer": str(gate.get("layer") or "abstain"),
        "bind": {
            "clock_ns": int(bind_st.get("clock_ns") or 0),
            "frame_seq": bind_st.get("frame_seq"),
            "path": str(bind_st.get("path") or "confirm"),
            "plane": str(bind_st.get("plane") or PLANE),
            "kind": str(bind_st.get("kind") or "hold"),
        },
    }


def apply_to_situation(situation: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    """Copy situation; strip unlicensed score keys. Never mutates the input bag."""
    out = dict(situation) if isinstance(situation, dict) else {}
    if not gate.get("licensed"):
        for k in _SCORE_KEYS:
            if k in out:
                out[k] = None
    return out


def gate_from_situation(situation: dict[str, Any] | None = None) -> dict[str, Any]:
    sit = situation if isinstance(situation, dict) else {}
    same = sit.get("same_seq")
    if same is not None:
        same = bool(same)
    live_clock = int(sit.get("clock_ns") or sit.get("live_clock_ns") or 0)
    ticket_clock = int(sit.get("confirm_clock_ns") or sit.get("ticket_clock_ns") or 0)
    frame_seq = sit.get("frame_seq")
    try:
        frame_seq_i = int(frame_seq) if frame_seq is not None else None
    except (TypeError, ValueError):
        frame_seq_i = None
    return license_digits(
        confirm_ticket_id=str(sit.get("confirm_ticket_id") or ""),
        score_vlm_locked=bool(sit.get("score_vlm_locked")),
        path=str(sit.get("path") or ""),
        ticket_crop_hash=str(sit.get("ticket_crop_hash") or sit.get("crop_hash") or ""),
        live_crop_hash=str(sit.get("crop_hash") or sit.get("live_crop_hash") or ""),
        same_seq=same,
        ticket_clock_ns=ticket_clock,
        live_clock_ns=live_clock,
        vlm_abstain=str(sit.get("vlm_status") or "").startswith("http_")
        or str(sit.get("last_reason") or "") == "abstain",
        frame_seq=frame_seq_i,
        home_score=sit.get("home_score", sit.get("score_home")),
        away_score=sit.get("away_score", sit.get("score_away")),
    )


SEQGATE_STATES = frozenset({"licensed", "hold"})


def _refuse_write(reason: str) -> dict[str, Any]:
    return {"accepted": False, "refuse": reason, "stamp": None, "entry": None}


def _stamp_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def accept_memory_write(entry: dict[str, Any] | None) -> dict[str, Any]:
    """Refuse unstamped session-brain / Qoremem writes. Fail closed.

    Required: clock_ns, frame_seq, crop_hash (key present; empty string allowed),
    path=fast|confirm, seqgate=licensed|hold, reason. ticket_id when licensed.
    """
    if not isinstance(entry, dict):
        return _refuse_write("unstamped")
    src = entry["stamp"] if isinstance(entry.get("stamp"), dict) else entry
    if "clock_ns" not in src or src.get("clock_ns") is None:
        return _refuse_write("unstamped")
    if "frame_seq" not in src or src.get("frame_seq") is None:
        return _refuse_write("unstamped")
    if "crop_hash" not in src or src.get("crop_hash") is None:
        return _refuse_write("unstamped")
    path = str(src.get("path") or "").lower()
    if path not in PATHS:
        return _refuse_write("unstamped")
    state = str(src.get("seqgate") or "").lower()
    if state not in SEQGATE_STATES:
        return _refuse_write("unstamped")
    reason = str(src.get("reason") or "").strip()
    if not reason:
        return _refuse_write("unstamped")
    clock_ns = _stamp_int(src.get("clock_ns"))
    frame_seq = _stamp_int(src.get("frame_seq"))
    if clock_ns is None or frame_seq is None:
        return _refuse_write("unstamped")
    if path == "fast" and state == "licensed":
        return _refuse_write("path_fast")
    ticket_id = str(src.get("ticket_id") or src.get("confirm_ticket_id") or "").strip()
    if state == "licensed" and not ticket_id:
        return _refuse_write("missing_ticket")
    stamp: dict[str, Any] = {
        "clock_ns": clock_ns,
        "frame_seq": frame_seq,
        "crop_hash": str(src.get("crop_hash")),
        "path": path,
        "seqgate": state,
        "reason": reason,
        "plane": PLANE,
    }
    if ticket_id:
        stamp["ticket_id"] = ticket_id
    out = dict(entry)
    out.update(stamp)
    return {"accepted": True, "refuse": None, "stamp": stamp, "entry": out}


def license_memory_speech(
    entry: dict[str, Any] | None,
    *,
    live_clock_ns: int = 0,
    live_frame_seq: int | None = None,
    live_crop_hash: str = "",
    score_vlm_locked: bool = False,
    home_score: Any = None,
    away_score: Any = None,
) -> dict[str, Any]:
    """Hard claims from memory only if SEQGATE still licenses that frame_seq.

    Never treats a historical seqgate=licensed as live speech. Stale → □–□.
    """
    try:
        live_seq = int(live_frame_seq) if live_frame_seq is not None else None
    except (TypeError, ValueError):
        live_seq = None
    checked = accept_memory_write(entry)
    if not checked["accepted"]:
        refuse = str(checked.get("refuse") or "unstamped")
        return {
            "licensed": False,
            "reason": refuse,
            "speech": NULL_DIGIT,
            "layer": "ticket" if refuse == "path_fast" else "abstain",
            "bind": bind(
                clock_ns=int(live_clock_ns or 0),
                frame_seq=live_seq,
                path="confirm",
                kind="veto" if refuse == "path_fast" else "hold",
            ),
        }
    stamp = checked["stamp"] or {}
    src = entry if isinstance(entry, dict) else {}
    path = str(stamp.get("path") or "confirm")
    hs = src.get("home_score") if home_score is None else home_score
    aws = src.get("away_score") if away_score is None else away_score
    if stamp.get("seqgate") == "hold" or path == "fast":
        reason = str(stamp.get("reason") or ("path_fast" if path == "fast" else "hold"))
        return {
            "licensed": False,
            "reason": reason,
            "speech": NULL_DIGIT,
            "layer": _REASON_LAYER.get(reason, "abstain"),
            "bind": bind(
                clock_ns=int(live_clock_ns or 0),
                frame_seq=live_seq,
                path=path,
                kind="veto" if path == "fast" or reason == "path_fast" else "hold",
            ),
        }
    mem_seq = stamp.get("frame_seq")
    same = False
    try:
        if mem_seq is not None and live_seq is not None:
            same = int(mem_seq) == int(live_seq)
    except (TypeError, ValueError):
        same = False
    locked = bool(score_vlm_locked) or bool(src.get("score_vlm_locked"))
    return license_digits(
        confirm_ticket_id=str(stamp.get("ticket_id") or ""),
        score_vlm_locked=locked,
        path=path,
        ticket_crop_hash=str(stamp.get("crop_hash") or ""),
        live_crop_hash=str(live_crop_hash or ""),
        same_seq=same,
        ticket_clock_ns=int(stamp.get("clock_ns") or 0),
        live_clock_ns=int(live_clock_ns or 0),
        frame_seq=live_seq,
        home_score=hs,
        away_score=aws,
    )


def memory_same_seq(entry: dict[str, Any] | None, live_frame_seq: Any) -> bool:
    """True only when memory.frame_seq equals the live FrameHub seq."""
    if not isinstance(entry, dict) or live_frame_seq is None:
        return False
    mem_seq = entry.get("frame_seq")
    try:
        return mem_seq is not None and int(mem_seq) == int(live_frame_seq)
    except (TypeError, ValueError):
        return False
