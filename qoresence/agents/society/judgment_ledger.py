"""Judgment ledger v0 — Society write sink for Jev / OCCF soft-act compose.

Schema ``qoresence.jev.ledger.v0``. Observation plane only.

One shared JSONL sink for the seven existing TypeSafe packs. Soft-act compose
lives in Python (OCCF), not in the model. Jev never mints digits:
``licenses_digits`` is False forever.

Bind row (frozen):

- agent turn ↔ ``clock_ns`` / ``frame_seq`` (or 0 if unbound)
- bind state: ``bound`` | ``stale`` | ``unbound`` | ``denied``
- tool + speech fields (observation language only)
- NO score integers, NO tickets, NO pixels

Fail-closed: missing clock → ``unbound`` / ``denied``, never invent a stamp
from the laptop monotonic clock or Muse VM time.

``--jev-connector`` / connector pack is NOT this module. Land order: ledger
first, connector later.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "qoresence.jev.ledger.v0"
PLANE = "qoresence-observation"
DEFAULT_OUT_DIR = "logs/jev_ledger"
DEFAULT_JSONL = "jev_ledger.jsonl"

# Seven existing packs (glass / join / mint widen PACKS later).
PACKS: tuple[str, ...] = (
    "conductor",
    "noul",
    "press",
    "recap",
    "coroner",
    "ticket_stale",
    "score_plausibility",
)

BIND_STATES: tuple[str, ...] = ("bound", "stale", "unbound", "denied")
SOFT_ACTIONS: tuple[str, ...] = ("act", "watch", "silent", "deny")
SPEECH_KINDS: tuple[str, ...] = ("none", "heat", "confirm_tokens", "boxes")
SOURCES: tuple[str, ...] = ("typesafe", "local_heuristic", "preflight", "off", "unknown")

# Closed observation-language tools (pack acts map into this catalog).
TOOLS: tuple[str, ...] = (
    "silent",
    "observe",
    "watch",
    "heat_chat",
    "board_observe",
    "press_label",
    "recap_inspect",
    "sync_diagnose",
    "stale_flag",
    "plausibility_veto",
    "refuse_actuator",
    "refuse_mid_drive_publish",
    "refuse_truth_claim",
)

_SCORE_PAIR = re.compile(r"\b\d{1,2}\s*[-–—:]\s*\d{1,2}\b")
_FORBIDDEN_KEY_FRAGMENTS = (
    "ticket_id",
    "confirm_ticket",
    "coupling_ticket",
    "home_score",
    "away_score",
    "score_home",
    "score_away",
    "jpeg",
    "png",
    "base64",
    "pixels",
    "frame_jpeg",
    "crop_jpeg",
    "hdmi",
    "thumbnail",
    "image",
    "api_key",
    "typesafe_key",
    "dualsense",
    "hid_report",
    "qortroller",
    "humanity",
    "eligibility",
    "anti_cheat",
    "truth_plane",
)

_lock = threading.Lock()
_jsonl_handle: Any = None
_jsonl_path: Path | None = None
_out_dir: str = DEFAULT_OUT_DIR
_rows = 0
_last: dict[str, Any] = {}
_enabled = True  # write sink accepts notes whenever packs call; cheap append


def reset_ledger_for_tests(*, out_dir: str | Path | None = None) -> None:
    """Close handles and optionally retarget the JSONL (tests only)."""
    global _jsonl_handle, _jsonl_path, _out_dir, _rows, _last, _enabled
    with _lock:
        if _jsonl_handle is not None:
            try:
                _jsonl_handle.close()
            except Exception:
                pass
        _jsonl_handle = None
        _jsonl_path = None
        _rows = 0
        _last = {}
        _enabled = True
        if out_dir is not None:
            _out_dir = str(out_dir)


def ledger_stats() -> dict[str, Any]:
    with _lock:
        return {
            "schema": SCHEMA,
            "plane": PLANE,
            "licenses_digits": False,
            "packs": list(PACKS),
            "rows": _rows,
            "path": str(_jsonl_path) if _jsonl_path else None,
            "last_bind": (_last.get("correlation") or {}).get("state"),
            "last_pack": _last.get("pack"),
        }


def _norm_clock_ns(v: Any) -> int:
    """Observatory clock only. Missing / invalid → 0 (never invent)."""
    if v in (None, "", False):
        return 0
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _norm_frame_seq(v: Any) -> int:
    if v in (None, "", False):
        return 0
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _scrub_value(v: Any) -> Any:
    if isinstance(v, str):
        return _SCORE_PAIR.sub("board", v)
    if isinstance(v, dict):
        return _scrub_dict(v)
    if isinstance(v, list):
        return [_scrub_value(x) for x in v[:32]]
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    return str(v)[:120]


def _key_forbidden(key: str) -> bool:
    k = key.lower()
    if k in {"score", "scores", "digits", "ticket", "tickets", "pixels", "frame", "crop"}:
        return True
    return any(frag in k for frag in _FORBIDDEN_KEY_FRAGMENTS)


def _scrub_dict(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in d.items():
        if not isinstance(key, str) or _key_forbidden(key):
            continue
        if isinstance(val, (int, float)) and key.lower() in {
            "home",
            "away",
            "home_score",
            "away_score",
        }:
            continue
        out[key] = _scrub_value(val)
    return out


def _map_tool(pack: str, tool: str | None, verdict: dict[str, Any]) -> str:
    t = (tool or "").strip()
    if t in TOOLS:
        return t
    # Pack-specific closed maps → observation language.
    if pack == "conductor":
        fa = str(verdict.get("fast_act") or "")
        if fa.startswith("chat_"):
            return "heat_chat"
        if str(verdict.get("observe") or "") == "board_licensed":
            return "board_observe"
        return "silent" if fa in {"", "silent"} else "observe"
    if pack == "noul":
        return "board_observe" if verdict.get("hud_kind") else "observe"
    if pack == "press":
        return "press_label"
    if pack == "recap":
        if verdict.get("hold") or verdict.get("truth_dest"):
            return "refuse_truth_claim" if verdict.get("truth_dest") else "recap_inspect"
        return "recap_inspect"
    if pack == "coroner":
        return "sync_diagnose"
    if pack == "ticket_stale":
        return "stale_flag" if verdict.get("action") == "flag_stale" else "observe"
    if pack == "score_plausibility":
        return "plausibility_veto" if verdict.get("action") == "flag_veto" else "observe"
    return "silent"


def _map_speech(pack: str, speech: str | None, verdict: dict[str, Any]) -> str:
    if speech in SPEECH_KINDS:
        return speech  # type: ignore[return-value]
    if pack == "conductor":
        if str(verdict.get("fast_act") or "").startswith("chat_"):
            return "heat"
        if str(verdict.get("observe") or "") == "board_licensed":
            return "confirm_tokens"
        return "none"
    if pack == "noul":
        speech_tok = str(verdict.get("board_speech") or "")
        if speech_tok in {"unlocked", "vlm_ungrounded", "menu", "vlm_none"}:
            return "boxes"
        if speech_tok == "confirm_ticket":
            return "confirm_tokens"
        return "none"
    if pack == "ticket_stale" and verdict.get("action") == "flag_stale":
        return "boxes"
    if pack == "score_plausibility" and verdict.get("action") == "flag_veto":
        return "boxes"
    if pack == "recap" and (verdict.get("digit_leak") or verdict.get("hold")):
        return "boxes"
    return "none"


def _map_action(
    pack: str,
    *,
    action: str | None,
    deny_reason: str | None,
    verdict: dict[str, Any],
) -> str:
    if deny_reason:
        return "deny"
    if action in SOFT_ACTIONS:
        return action  # type: ignore[return-value]
    # Pack action vocab → soft-act.
    raw = str(action or verdict.get("action") or "")
    if pack == "conductor":
        fa = str(verdict.get("fast_act") or "silent")
        if fa == "silent" and str(verdict.get("observe") or "silent") == "silent":
            return "silent"
        if fa.startswith("chat_") or fa in {"consider_clip", "arm_prediction"}:
            return "act"
        return "watch"
    if pack == "press":
        out = str(verdict.get("outcome") or "")
        if out == "labeled":
            return "act"
        if out == "eaten":
            return "watch"
        return "silent"
    if pack == "recap":
        return "deny" if verdict.get("hold") else "silent"
    if pack == "coroner":
        if raw == "apply":
            return "act"
        if raw in {"observe_low_conf", "held_transient"}:
            return "watch"
        return "silent"
    if pack == "ticket_stale":
        if raw == "flag_stale":
            return "watch"
        if raw == "watch":
            return "watch"
        return "silent"
    if pack == "score_plausibility":
        if raw == "flag_veto":
            return "watch"
        if raw == "watch":
            return "watch"
        return "silent"
    if pack == "noul":
        return "watch" if verdict.get("hud_kind") else "silent"
    if raw in {"act", "apply", "flag_stale", "flag_veto", "labeled"}:
        return "act" if raw in {"act", "apply", "labeled"} else "watch"
    if raw in {"watch", "observe_low_conf", "held_transient", "eaten"}:
        return "watch"
    if raw in {"deny", "hold"}:
        return "deny"
    return "silent"


def compose_soft_act(
    *,
    pack: str,
    tool: str | None = None,
    action: str | None = None,
    speech: str | None = None,
    clock_ns: int | None = None,
    frame_seq: int | None = None,
    deny_reason: str | None = None,
    stale: bool = False,
    source: str = "local_heuristic",
    agent: dict[str, Any] | None = None,
    tool_confidence: float | None = None,
    verdict: dict[str, Any] | None = None,
    session_id: str = "",
    bind_id: str = "",
) -> dict[str, Any]:
    """Python OCCF soft-act compose. Fail-closed bind. Never licenses digits.

    ``clock_ns`` / ``frame_seq`` must come from the observatory (FrameHub /
    pack evidence). Pass 0 / omit when unbound — do not substitute monotonic.
    """
    v = dict(verdict or {})
    if pack not in PACKS:
        # Unknown pack → denied row (no connector pack yet).
        deny_reason = deny_reason or "unknown_pack"
        pack_name = str(pack)[:32] or "unknown"
    else:
        pack_name = pack

    c_ns = _norm_clock_ns(clock_ns if clock_ns is not None else v.get("clock_ns"))
    f_seq = _norm_frame_seq(frame_seq if frame_seq is not None else v.get("frame_seq"))

    mapped_tool = _map_tool(pack if pack in PACKS else "conductor", tool, v)
    mapped_action = _map_action(
        pack if pack in PACKS else "conductor",
        action=action,
        deny_reason=deny_reason,
        verdict=v,
    )
    mapped_speech = _map_speech(pack if pack in PACKS else "conductor", speech, v)
    src = source if source in SOURCES else "unknown"

    # Correlation fail-closed.
    if deny_reason or mapped_action == "deny" or pack not in PACKS:
        bind_state = "denied"
        if not deny_reason:
            deny_reason = "denied"
        # Denied rows still may carry a clock if known, but never invent one.
        method = "none"
    elif stale or (
        pack == "ticket_stale" and str(v.get("action") or "") == "flag_stale"
    ):
        bind_state = "stale"
        method = "live_pull" if c_ns > 0 else "none"
        mapped_speech = "boxes" if mapped_speech == "confirm_tokens" else mapped_speech
    elif c_ns <= 0 and f_seq <= 0:
        bind_state = "unbound"
        method = "none"
        # Unbound must not pretend confirm speech.
        if mapped_speech == "confirm_tokens":
            mapped_speech = "boxes"
    else:
        bind_state = "bound"
        method = "live_pull"

    agent_row = {
        "brand": str((agent or {}).get("brand") or "unknown")[:32],
        "turn_id": str((agent or {}).get("turn_id") or "")[:64],
        "asked_at_unix_ms": int((agent or {}).get("asked_at_unix_ms") or 0),
    }

    row: dict[str, Any] = {
        "schema": SCHEMA,
        "plane": PLANE,
        "licenses_digits": False,
        "pack": pack_name if pack in PACKS else str(pack)[:32],
        "bind_id": str(bind_id or "")[:64],
        "session_id": str(session_id or "")[:64],
        "agent": agent_row,
        "observatory": {
            "clock_ns": c_ns if bind_state != "unbound" else (c_ns if c_ns > 0 else 0),
            "frame_seq": f_seq if bind_state != "unbound" else (f_seq if f_seq > 0 else 0),
        },
        "intent": {
            "tool": mapped_tool,
            "tool_confidence": (
                round(float(tool_confidence), 3) if tool_confidence is not None else None
            ),
        },
        "compose": {
            "action": mapped_action if bind_state != "denied" else "deny",
            "deny_reason": deny_reason,
            "speech": mapped_speech if bind_state != "denied" else "none",
        },
        "correlation": {
            "state": bind_state,
            "method": method,
        },
        "source": src,
        "noted_at_unix_ms": int(time.time() * 1000),
    }

    # Unbound: force clocks to 0 (do not leave a half-stamp).
    if bind_state == "unbound":
        row["observatory"]["clock_ns"] = 0
        row["observatory"]["frame_seq"] = 0

    return _assert_row_invariants(row)


def _assert_row_invariants(row: dict[str, Any]) -> dict[str, Any]:
    """Hard invariants on every ledger row."""
    row["licenses_digits"] = False
    row["plane"] = PLANE
    row["schema"] = SCHEMA
    corr = row.setdefault("correlation", {})
    if corr.get("state") not in BIND_STATES:
        corr["state"] = "unbound"
    compose = row.setdefault("compose", {})
    if compose.get("action") not in SOFT_ACTIONS:
        compose["action"] = "silent"
    if compose.get("speech") not in SPEECH_KINDS:
        compose["speech"] = "none"
    intent = row.setdefault("intent", {})
    if intent.get("tool") not in TOOLS:
        intent["tool"] = "silent"
    # Strip any accidental leakage from nested agent blobs.
    row["agent"] = _scrub_dict(dict(row.get("agent") or {}))
    # Ensure no score-pair text in speech/deny fields.
    for path in (("compose", "deny_reason"),):
        cur: Any = row
        for p in path[:-1]:
            cur = cur.get(p) if isinstance(cur, dict) else None
        if isinstance(cur, dict) and isinstance(cur.get(path[-1]), str):
            cur[path[-1]] = _SCORE_PAIR.sub("board", cur[path[-1]])
    return row


def row_has_leakage(row: dict[str, Any]) -> list[str]:
    """Return leakage reasons if score/ticket/pixel material is present."""
    reasons: list[str] = []
    blob = json.dumps(row, default=str)
    if _SCORE_PAIR.search(blob):
        reasons.append("score_pair")
    lower = blob.lower()
    for frag in (
        "ticket_id",
        "confirm_ticket",
        "home_score",
        "away_score",
        "base64",
        "crop_jpeg",
        "frame_jpeg",
        "pixels",
    ):
        if frag in lower:
            reasons.append(frag)
    if row.get("licenses_digits") is not False:
        reasons.append("licenses_digits")
    return reasons


def _ensure_handle() -> Any:
    global _jsonl_handle, _jsonl_path
    if _jsonl_handle is not None:
        return _jsonl_handle
    try:
        out = Path(_out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / DEFAULT_JSONL
        _jsonl_handle = path.open("a", encoding="utf-8")
        _jsonl_path = path
    except Exception as e:
        log.debug("judgment ledger jsonl not opened: %s", e)
        _jsonl_handle = None
        _jsonl_path = None
    return _jsonl_handle


def note_judgment(
    pack: str,
    *,
    verdict: dict[str, Any] | None = None,
    tool: str | None = None,
    action: str | None = None,
    speech: str | None = None,
    clock_ns: int | None = None,
    frame_seq: int | None = None,
    deny_reason: str | None = None,
    stale: bool = False,
    source: str | None = None,
    agent: dict[str, Any] | None = None,
    tool_confidence: float | None = None,
    session_id: str = "",
    bind_id: str = "",
) -> dict[str, Any]:
    """Compose a ledger row and append to the Society write sink.

    Safe to call from pack workers. Never raises into callers. Never emits
    bus events. Never licenses digits.
    """
    v = dict(verdict or {})
    src = source or str(v.get("source") or "unknown")
    try:
        row = compose_soft_act(
            pack=pack,
            tool=tool,
            action=action,
            speech=speech,
            clock_ns=clock_ns,
            frame_seq=frame_seq,
            deny_reason=deny_reason,
            stale=stale,
            source=src,
            agent=agent,
            tool_confidence=tool_confidence,
            verdict=v,
            session_id=session_id,
            bind_id=bind_id,
        )
    except Exception as e:
        log.debug("judgment compose failed: %s", e)
        row = compose_soft_act(
            pack="conductor" if pack not in PACKS else pack,
            deny_reason="compose_error",
            source="preflight",
            clock_ns=0,
            frame_seq=0,
        )
        row["pack"] = pack if pack in PACKS else str(pack)[:32]
        row["correlation"]["state"] = "denied"

    # Final scrub — drop any forbidden keys that snuck in via agent.
    leaks = row_has_leakage(row)
    if leaks:
        row["compose"]["deny_reason"] = row["compose"].get("deny_reason") or "scrubbed_leak"
        # Re-compose unbound/denied without verdict blob.
        row = compose_soft_act(
            pack=pack if pack in PACKS else "conductor",
            tool=row.get("intent", {}).get("tool"),
            action="deny",
            speech="none",
            clock_ns=0,
            frame_seq=0,
            deny_reason="scrubbed_leak",
            source="preflight",
        )
        row["pack"] = pack if pack in PACKS else str(pack)[:32]

    global _rows, _last
    with _lock:
        if not _enabled:
            _last = row
            return row
        handle = _ensure_handle()
        if handle is not None:
            try:
                handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
                handle.flush()
                _rows += 1
            except Exception:
                pass
        _last = row
    return row


def note_pack_verdict(
    pack: str,
    verdict: dict[str, Any] | None,
    *,
    clock_ns: int | None = None,
    frame_seq: int | None = None,
    stale: bool = False,
    deny_reason: str | None = None,
    session_id: str = "",
) -> dict[str, Any] | None:
    """Thin pack hook: map a pack compose dict onto the ledger.

    Packs call this after their own compose / JSONL write. Missing clock
    fail-closes to unbound (or denied when ``deny_reason`` set).
    """
    if not verdict or not isinstance(verdict, dict):
        return None
    try:
        return note_judgment(
            pack,
            verdict=verdict,
            clock_ns=clock_ns,
            frame_seq=frame_seq,
            stale=stale,
            deny_reason=deny_reason,
            source=str(verdict.get("source") or "unknown"),
            session_id=session_id,
        )
    except Exception as e:
        log.debug("note_pack_verdict skipped: %s", e)
        return None
