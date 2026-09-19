"""OCCF slice 3 — smallest pull-only localhost MCP for personal agents.

Observatory connector surface (``docs/OCCF.md``). One read tool —
``get_observation`` — plus closed ``refuse_*`` tools so a personal agent
(Muse first) can never invent actuators. This is the *read* half only; the
``qoresence.connector-bind.v0`` writer is a separate slice and stays out.

Hard law:

- Plane ``qoresence-observation``. ``licenses_digits`` is False on every
  payload, forever — the connector never mints *and never echoes* score
  digits. A SEQGATE-licensed board reports ``score.claim`` only; the
  integers stay on the ConfirmTicket, not on this API.
- Pull-only. Never opens capture, never touches DualSense/pad, never
  publishes mid-drive, never wraps to a truth plane.
- Localhost only. State is pulled from the AgentGlass snapshot on
  ``127.0.0.1`` (stdio transport — no socket of its own).
- Default OFF / opt-in: ``QORESENCE_OCCF=1`` or ``--occf``. ``--play``
  does not enable it and has no wiring to it.
- Fail-closed: board unlocked / no session / ledger off → blank tokens
  and ``must_not_invent`` entries, never a guess.
- No ``get_timeline``, no ``export_presence_pack``, no directory/Pages.
  Pattern B (Qoresence owns capture) unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from typing import Any

from qoresence.mcp.server import _rpc_error, _rpc_result

log = logging.getLogger(__name__)

SERVER_NAME = "qoresence-observatory"
SERVER_VERSION = "0.1.0-dev"
SCHEMA = "qoresence.occf-mcp.v0"
PLANE = "qoresence-observation"

ENV_ENABLE = "QORESENCE_OCCF"
_ON = {"1", "true", "on", "yes"}

# Score-pair pattern: "21-17", "14–10". Clock/seq ints are correlation
# tokens, not score digits, and stay. IPs/ports have no dash pair.
_SCORE_PAIR = re.compile(r"\b\d+\s*[-–]\s*\d+\b")

_cli_enabled = False


def occf_enabled() -> bool:
    """Opt-in gate. ``QORESENCE_OCCF=1`` or the ``--occf`` CLI flag."""
    return _cli_enabled or os.environ.get(ENV_ENABLE, "").strip().lower() in _ON


def scrub_licenses_digits(obj: Any) -> Any:
    """Deep-copy ``obj`` forcing every ``licenses_digits`` key to False."""
    if isinstance(obj, dict):
        return {
            k: (False if k == "licenses_digits" else scrub_licenses_digits(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [scrub_licenses_digits(v) for v in obj]
    return obj


def _redact_score_strings(obj: Any) -> Any:
    """Replace every score-pair string (``14-10``) with ``□–□``, recursively.

    Catches digit echoes outside ``score`` — e.g. the SEQGATE receipt's
    ``speech`` field carries the licensed digit string when the board is
    locked. The token survives; the digits do not.
    """
    if isinstance(obj, str):
        return _SCORE_PAIR.sub("□–□", obj)
    if isinstance(obj, dict):
        return {k: _redact_score_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_score_strings(v) for v in obj]
    return obj


def _strip_score_digits(out: dict[str, Any]) -> None:
    """Never echo score digits on this plane — claim token only."""
    score = out.get("score")
    if isinstance(score, dict):
        claim = bool(score.get("claim"))
        out["score"] = {"claim": claim, "home": None, "away": None}
        if claim:
            out.setdefault("must_not_invent", [])
            if "score_digits_not_echoed" not in out["must_not_invent"]:
                out["must_not_invent"].append("score_digits_not_echoed")
    may_say = out.get("may_say")
    if isinstance(may_say, list):
        out["may_say"] = [
            line
            for line in may_say
            if not (isinstance(line, str) and _SCORE_PAIR.search(line))
        ]
    redacted = _redact_score_strings(out)
    out.clear()
    out.update(redacted)


def _blank_observation() -> dict[str, Any]:
    return {
        "ok": False,
        "schema": SCHEMA,
        "plane": PLANE,
        "licenses_digits": False,
        "claim_ceiling": "observation_only",
        "title": {"claim": False, "profile": None, "hysteresis": None},
        "score": {"claim": False, "home": None, "away": None},
        "pad": {"phrase": None, "coupling": None, "frame_seq": None},
        "clock_ns": None,
        "seq": None,
        "may_say": [],
        "must_not_invent": ["no_observation"],
    }


def _tail_row(row: dict[str, Any]) -> dict[str, Any]:
    """Token-only projection — pack/action/source + clock. No verdict body.

    Connector rows (``pack="connector"``) carry ``compose.action`` /
    ``correlation.state`` instead of ``verdict.action`` — same tokens.
    """
    verdict = row.get("verdict") if isinstance(row.get("verdict"), dict) else {}
    compose = verdict.get("compose") if isinstance(verdict.get("compose"), dict) else {}
    corr = verdict.get("correlation") if isinstance(verdict.get("correlation"), dict) else {}
    action = verdict.get("action")
    if not isinstance(action, str):
        action = compose.get("action")
    return {
        "pack": row.get("pack"),
        "action": action if isinstance(action, str) else None,
        "state": corr.get("state") if isinstance(corr.get("state"), str) else None,
        "source": verdict.get("source") if isinstance(verdict.get("source"), str) else None,
        "clock_ns": row.get("clock_ns"),
        "frame_seq": row.get("frame_seq"),
        "ts": row.get("ts"),
        "licenses_digits": False,
    }


def _jev_tail(limit: int) -> dict[str, Any]:
    """Last ``limit`` ledger rows as tokens. Empty unless ledger enabled."""
    limit = max(1, min(20, int(limit)))
    try:
        from qoresence.observability.jev_ledger import (
            DEFAULT_PATH,
            ledger_enabled,
            read_judgments,
        )
    except Exception:
        return {"enabled": False, "rows": []}
    if not ledger_enabled():
        return {"enabled": False, "rows": []}
    path = os.environ.get("QORESENCE_JEV_LEDGER_PATH") or str(DEFAULT_PATH)
    rows = [_tail_row(r) for r in list(read_judgments(path))[-limit:]]
    return {"enabled": True, "rows": rows}


def _observatory_from_pack(pack: dict[str, Any], snap: dict[str, Any]) -> dict[str, Any]:
    """Observatory snapshot for a connector bind, built from the witness
    read just served — one truth path, never the guest clock."""
    title = pack.get("title") if isinstance(pack.get("title"), dict) else {}
    score = pack.get("score") if isinstance(pack.get("score"), dict) else {}
    pad = pack.get("pad") if isinstance(pack.get("pad"), dict) else {}
    video = pack.get("video") if isinstance(pack.get("video"), dict) else {}
    glass = pack.get("glass") if isinstance(pack.get("glass"), dict) else {}
    session = snap.get("session") if isinstance(snap.get("session"), dict) else {}
    has_frame = bool(video.get("has_frame"))
    return {
        "clock_ns": int(pack.get("clock_ns") or 0),
        "frame_seq": video.get("frame_seq") or pad.get("frame_seq") or pack.get("seq"),
        "title_lock": "locked" if title.get("claim") else "unlocked",
        "board_lock": "locked" if score.get("claim") else "unlocked",
        "last_confirm": "present" if score.get("claim") else "absent",
        "coupling": "present" if pad.get("coupling") else "absent",
        "climax_ready": False,
        "live": has_frame,
        "has_frame": has_frame,
        "lan_opt_in": bool(glass.get("lan")),
        "session_id": session.get("session_id"),
    }


def _closed_bind(reason: str) -> dict[str, Any]:
    return {
        "state": "unbound",
        "method": "none",
        "recorded": False,
        "reason": reason,
        "deny_reason": None,
        "speech": None,
        "bind_id": None,
        "source": None,
        "session_id": None,
        "licenses_digits": False,
    }


def _bind_for_turn(
    turn: dict[str, Any], pack: dict[str, Any], snap: dict[str, Any]
) -> dict[str, Any]:
    """Correlate one agent turn via OCCF slice-2 ``note_agent_turn``.

    Soft dependency: when the connector module, engine, or env is absent
    the turn is simply unbound — never a fabricated correlation. A state
    of ``bound`` is only reported when a ``pack="connector"`` row was
    actually written (engine on AND session_id present). Deny reasons
    always surface — a refuse does not need a ledger row to be binding.
    """
    try:
        from qoresence.observability.connector_bind import (
            get_connector_bind,
            make_connector_from_config,
            note_agent_turn,
        )
    except Exception:
        return _closed_bind("connector_unavailable")
    try:
        eng = get_connector_bind() or make_connector_from_config(None)
        if eng is None:
            return _closed_bind("connector_off")
        obs = _observatory_from_pack(pack, snap if isinstance(snap, dict) else {})
        sid = str(turn.get("session_id") or obs.get("session_id") or "")
        bind = note_agent_turn(
            dict(turn), observatory=obs, session_id=sid or None
        )
    except Exception:
        return _closed_bind("bind_failed")
    if not isinstance(bind, dict):
        return _closed_bind("no_bind")
    corr = bind.get("correlation") if isinstance(bind.get("correlation"), dict) else {}
    comp = bind.get("compose") if isinstance(bind.get("compose"), dict) else {}
    deny = comp.get("deny_reason")
    recorded = bool(sid)  # note_judgment only writes when a session exists
    state = str(corr.get("state") or "unbound")
    return {
        "state": state if recorded else ("denied" if deny else "unbound"),
        "method": corr.get("method") if recorded else "none",
        "recorded": recorded,
        "reason": None if recorded else ("not_recorded" if deny else "no_session"),
        "deny_reason": deny,
        "speech": comp.get("speech"),
        "bind_id": bind.get("bind_id"),
        "source": bind.get("source"),
        "session_id": bind.get("session_id") or sid or None,
        "licenses_digits": False,
    }


def handle_get_observation(
    jev_tail: int = 0, agent_turn: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Witness read: what the agent may say right now. Reuses the live
    ``build_observation`` path — there is no second truth path.

    ``agent_turn`` is optional guest annotation for the connector bind
    (``--jev-connector`` / ``QORESENCE_JEV_CONNECTOR=1``). The answer is
    fail-closed: without a real ``pack="connector"`` row the response
    reports ``bind.state=unbound``.
    """
    from qoresence.mcp import server as _glass

    out = _blank_observation()
    try:
        pack = _glass.handle_get_observation()
    except Exception as e:
        out["error"] = "observation_failed"
        out["hint"] = str(e)
        return scrub_licenses_digits(out)
    if isinstance(pack, dict):
        out.update(pack)
    out["schema"] = SCHEMA
    out["plane"] = PLANE
    out["licenses_digits"] = False
    if not isinstance(out.get("may_say"), list):
        out["may_say"] = []
    if not isinstance(out.get("must_not_invent"), list):
        out["must_not_invent"] = ["no_observation"]
    if int(jev_tail or 0) > 0:
        out["jev_tail"] = _jev_tail(int(jev_tail))
    _strip_score_digits(out)
    if isinstance(agent_turn, dict) and agent_turn:
        snap: dict[str, Any] = {}
        try:
            snap = _glass.handle_get_snapshot()
        except Exception:
            snap = {}
        out["bind"] = _bind_for_turn(dict(agent_turn), out, snap)
    return scrub_licenses_digits(out)


def handle_refuse_actuator() -> dict[str, Any]:
    """Closed deny for pad / DualSense / capture-control asks."""
    return {
        "ok": False,
        "schema": SCHEMA,
        "plane": PLANE,
        "licenses_digits": False,
        "deny_reason": "pad_not_on_this_plane",
        "say": "Qoresence observes the session; the agent never takes the pad.",
        "may_say": ["the agent cannot control the game"],
        "must_not_invent": ["pad_input", "capture_control", "actuator"],
    }


def handle_refuse_mid_drive_publish() -> dict[str, Any]:
    """Closed deny for publish / share / upload asks during play."""
    return {
        "ok": False,
        "schema": SCHEMA,
        "plane": PLANE,
        "licenses_digits": False,
        "deny_reason": "mid_drive_publish",
        "say": "Qoresence never publishes mid-drive because an agent asked.",
        "may_say": ["nothing was published"],
        "must_not_invent": ["mid_drive_publish", "auto_highlight", "public_url"],
    }


def _disabled_result() -> dict[str, Any]:
    return {
        "ok": False,
        "schema": SCHEMA,
        "plane": PLANE,
        "licenses_digits": False,
        "error": "occf_disabled",
        "hint": f"set {ENV_ENABLE}=1 (or --occf) to opt in; --play never enables this",
        "may_say": [],
        "must_not_invent": ["occf_disabled"],
    }


TOOL_DEFS = [
    {
        "name": "get_observation",
        "description": (
            "Pull-only witness read on plane qoresence-observation: what the "
            "agent MAY say right now (may_say) and what it must never invent "
            "(must_not_invent). Fail-closed blanks when the board is unlocked "
            "or no session is live. Score digits are never echoed — "
            "licenses_digits=false forever. Optional jev_tail (0..20) appends "
            "token-only Jev ledger rows when the ledger is enabled."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "jev_tail": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 20,
                    "default": 0,
                    "description": "Append last N qoresence.jev.ledger.v0 rows as {pack,action,source,state} tokens.",
                },
                "agent_turn": {
                    "type": "object",
                    "description": (
                        "Optional agent-turn annotation for the OCCF connector bind "
                        "(--jev-connector / QORESENCE_JEV_CONNECTOR=1). Guest clock "
                        "only — asked_at_unix_ms never stamps observatory clock_ns. "
                        "Response reports bind.state; unbound when no pack=connector "
                        "row exists."
                    ),
                    "properties": {
                        "utterance": {"type": "string"},
                        "brand": {"type": "string"},
                        "turn_id": {"type": "string"},
                        "asked_at_unix_ms": {"type": "integer"},
                        "echo_frame_seq": {"type": "integer"},
                        "chapter_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "tool": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "refuse_actuator",
        "description": (
            "Closed deny for any ask to move the pad, DualSense, capture, or "
            "the game. The agent observes only — deny_reason "
            "pad_not_on_this_plane. No side effects."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "refuse_mid_drive_publish",
        "description": (
            "Closed deny for publish / share / upload asks. Qoresence never "
            "publishes mid-drive because an agent asked. deny_reason "
            "mid_drive_publish. No side effects."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]

HANDLERS = {
    "get_observation": lambda a: handle_get_observation(
        jev_tail=int(a.get("jev_tail", 0) or 0),
        agent_turn=a.get("agent_turn") if isinstance(a.get("agent_turn"), dict) else None,
    ),
    "refuse_actuator": lambda a: handle_refuse_actuator(),
    "refuse_mid_drive_publish": lambda a: handle_refuse_mid_drive_publish(),
}


def _handle_request(msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}
    is_notif = "id" not in msg
    if method == "initialize":
        return _rpc_result(
            req_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "occf": {
                    "enabled": occf_enabled(),
                    "plane": PLANE,
                    "licenses_digits": False,
                },
            },
        )
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "tools/list":
        return _rpc_result(req_id, {"tools": TOOL_DEFS if occf_enabled() else []})
    if method == "resources/list":
        return _rpc_result(req_id, {"resources": []})
    if method == "prompts/list":
        return _rpc_result(req_id, {"prompts": []})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if not occf_enabled():
            return _rpc_result(
                req_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(_disabled_result(), indent=2),
                        }
                    ],
                    "isError": True,
                },
            )
        h = HANDLERS.get(name)
        if not h:
            return _rpc_error(req_id, -32601, f"unknown tool: {name}")
        try:
            result = h(args)
            text = json.dumps(result, indent=2, default=str)
            return _rpc_result(req_id, {"content": [{"type": "text", "text": text}]})
        except Exception as e:
            log.exception("tools/call %s failed", name)
            return _rpc_error(req_id, -32603, f"tool {name} failed: {e}")
    if method == "ping":
        return _rpc_result(req_id, {})
    if is_notif:
        return None
    return _rpc_error(req_id, -32601, f"Method not found: {method}")


def _serve_stdio() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if isinstance(msg, list):
            rs = []
            for m in msg:
                r = _handle_request(m)
                if r is not None:
                    rs.append(r)
            if rs:
                sys.stdout.write(json.dumps(rs) + "\n")
                sys.stdout.flush()
        else:
            resp = _handle_request(msg)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()


def main() -> None:
    import argparse

    global _cli_enabled
    p = argparse.ArgumentParser(
        description="Qoresence OCCF observatory MCP — pull-only, localhost, opt-in"
    )
    p.add_argument(
        "--occf",
        action="store_true",
        help=f"opt in to the observatory connector surface (also {ENV_ENABLE}=1)",
    )
    p.add_argument("--help-tools", action="store_true", help="list tools and exit")
    args = p.parse_args()
    if args.help_tools:
        print(json.dumps(TOOL_DEFS, indent=2))  # noqa: T201
        return
    if args.occf:
        _cli_enabled = True
    if not occf_enabled():
        log.warning(
            "OCCF MCP started without opt-in — tools stay hidden until %s=1 or --occf",
            ENV_ENABLE,
        )
    _serve_stdio()


if __name__ == "__main__":
    main()
