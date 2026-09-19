"""OCCF connector bind — correlate an agent turn to an observatory instant.

Schema ``qoresence.connector-bind.v0`` on plane ``qoresence-observation``.
Source of truth: ``docs/OCCF.md`` (objects -> connector bind, correlation
states, synchronization methods, TypeSafe door). One bind row per *accepted
or refused* agent turn; Muse is the first personal agent, the contract is
agent-generic.

Hard law:

- ``licenses_digits`` is False on every bind, forever. Score integers,
  ticket bodies, crop pixels, keys, HDMI JPEGs, DualSense reports, and Recap
  envelope blobs are forbidden on the row.
- The guest clock is annotation only: ``agent.asked_at_unix_ms`` never
  stamps ``observatory.clock_ns`` (no ``muse_vm_time`` method exists).
- SyncGlass pad<->picture binds are not OCCF agent<->session binds; this
  module never reads SyncGlass rows as correlation evidence.
- Binds are written **only** through the unified Jev ledger as
  ``pack="connector"`` (``note_judgment``). There is no ``connector.jsonl``.
  Enabling the connector ensures the ledger is on for these rows.
- Default OFF. ``--jev-connector`` / ``QORESENCE_JEV_CONNECTOR=1``.
  ``--play`` does not enable it. Localhost pull-only; fail-closed.
- No bus emits, no lobe locks, no pad ownership. The agent never takes
  the pad.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import uuid
from typing import Any

from qoresence.observability.connector_bind_questions import (
    NEEDS_TOOL_MIN,
    NOUL_DENY,
    NOUL_SOFT,
    NOULS,
    RISK_ACTUATOR_OR_EXFIL,
    TOOL_CONF_MIN,
    TOOLS,
    connector_bind_questions,
)
from qoresence.observability.jev_ledger import (
    configure_jev_ledger,
    note_judgment,
)
from qoresence.observability.typesafe_ask import (
    DEFAULT_TIMEOUT_S,
    key_present,
    system_one,
)

log = logging.getLogger(__name__)

SCHEMA = "qoresence.connector-bind.v0"
PLANE = "qoresence-observation"

AGENT_BRANDS = frozenset({"muse", "grok", "claude", "unknown"})
CORRELATION_STATES = frozenset({"bound", "unbound", "stale", "denied"})
# Ordered, fail-closed. First match wins. No muse_vm_time / wall_clock_guess /
# pad_event_id / sync_glass_bind method exists.
SYNC_METHODS = ("live_pull", "seq_match", "chapter_id", "recap_door", "none")
DENY_REASONS = frozenset(
    {
        "pad_not_on_this_plane",
        "mid_drive",
        "localhost_only",
        "actuator_or_exfil",
        "off_plane_wrap",
    }
)
COMPOSE_ACTIONS = frozenset({"act", "watch", "silent", "deny"})
SPEECH_KINDS = frozenset({"none", "heat", "confirm_tokens", "boxes"})
SOURCES = frozenset({"typesafe", "local_heuristic", "preflight", "off"})

_LOCK_KINDS = frozenset({"locked", "unlocked", "unknown"})
_PRESENCE = frozenset({"present", "absent"})
# Wrap dests an agent turn may legitimately reach for; anything else is an
# off-plane wrap ask and denied. ``qortroller-truth`` is never out.
_ALLOWED_WRAP_DESTS = frozenset({"qoresence-research"})
# ticket_stale drift classes (not fresh / not unknown) — STALE state source.
_STALE_CLASSES = frozenset(
    {"crop_moved_on", "match_changed", "menu_or_plate", "clock_drift"}
)

DEFAULT_SEQ_MATCH_WINDOW = 1800  # frames (~30s at 60fps) an echoed seq may lag

_PAD_WORDS = (
    "press", "button", "dualsense", "controller", "joystick", "pad",
    "make him", "throw it", "run the play", "hike", "call a play",
)
_PUBLISH_WORDS = (
    "publish", "post", "tweet", "share", "broadcast", "upload",
    "stream it", "twitch", "discord", "tiktok", "youtube",
)
_OFFBOX_WORDS = (
    "cloud", "public url", "online", "internet", "remote", "off the box",
    "off this machine", "leave localhost", "webhook",
)
_DIGIT_WORDS = (
    "score", "digits", "points", "winning", "losing", "how many",
)
_PACK_WORDS = ("presence pack", "take it with", "export", "pack this", "zip")
_CLIP_WORDS = ("clip", "highlight", "that play", "the play")
_TIMELINE_WORDS = ("timeline", "what happened", "recap", "that drive", "earlier")
_LIVE_WORDS = (
    "right now", "what's happening", "whats happening", "live",
    "observation", "going on", "on screen", "board",
)
_HEAT_WORDS = ("hype", "insane", "crazy", "let's go", "lets go", "huge", "clutch")
_SCORE_ASSERT_RE = re.compile(r"\b\d{1,3}\s*[-–—to]+\s*\d{1,3}\b")


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_JEV_CONNECTOR", "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }


def _num(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _f(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _lock_kind(v: Any) -> str:
    if isinstance(v, bool):
        return "locked" if v else "unlocked"
    s = str(v or "").strip().lower()
    return s if s in _LOCK_KINDS else "unknown"


def _presence(v: Any) -> str:
    if isinstance(v, bool):
        return "present" if v else "absent"
    s = str(v or "").strip().lower()
    if s in _PRESENCE:
        return s
    return "present" if s in {"yes", "true", "1", "on"} else "absent"


def _norm_brand(v: Any) -> str:
    s = str(v or "").strip().lower()
    return s if s in AGENT_BRANDS else "unknown"


def _norm_tool(v: Any) -> str:
    s = str(v or "").strip().lower()
    return s if s in TOOLS else "silent"


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def normalize_agent(turn: dict[str, Any]) -> dict[str, Any]:
    """Guest annotation only — asked_at_unix_ms never becomes clock_ns."""
    turn = turn if isinstance(turn, dict) else {}
    return {
        "brand": _norm_brand(
            turn.get("brand") or turn.get("agent_brand") or turn.get("agent")
        ),
        "turn_id": str(turn.get("turn_id") or ""),
        "asked_at_unix_ms": _num(turn.get("asked_at_unix_ms")) or 0,
    }


def normalize_observatory(obs: dict[str, Any] | None) -> dict[str, Any]:
    """Snapshot of the observatory at bind time (never the guest clock)."""
    obs = obs if isinstance(obs, dict) else {}
    frame_seq = _num(obs.get("frame_seq") if obs.get("frame_seq") is not None else obs.get("seq"))
    clock_ns = _num(obs.get("clock_ns"))
    last_confirm = obs.get("last_confirm")
    if last_confirm is None:
        last_confirm = obs.get("has_confirm")
    coupling = obs.get("coupling")
    if coupling is None:
        coupling = obs.get("has_coupling")
    return {
        "clock_ns": int(clock_ns or 0),
        "frame_seq": frame_seq,
        "crop_hash": obs.get("crop_hash"),
        "title_lock": _lock_kind(obs.get("title_lock")),
        "board_lock": _lock_kind(obs.get("board_lock")),
        "last_confirm": _presence(last_confirm),
        "coupling": _presence(coupling),
        "climax_ready": bool(obs.get("climax_ready")),
        "live": bool(obs.get("live")),
        "has_frame": bool(obs.get("has_frame")) or frame_seq is not None,
        "lan_opt_in": bool(obs.get("lan_opt_in")),
        "ticket_stale": bool(obs.get("ticket_stale"))
        or str(obs.get("stale_class") or "") in _STALE_CLASSES,
        "recap_open": bool(obs.get("recap_open")),
        "recap_clock_commitment": _num(obs.get("recap_clock_commitment")),
        "recap_witness_hash": obs.get("recap_witness_hash"),
        "chapters": obs.get("chapters") if isinstance(obs.get("chapters"), dict) else {},
        "seq_lo": _num(obs.get("seq_lo")),
        "seq_hi": _num(obs.get("seq_hi")),
        "seq_clocks": obs.get("seq_clocks") if isinstance(obs.get("seq_clocks"), dict) else {},
        "witness_hash": obs.get("witness_hash"),
        "session_id": obs.get("session_id"),
    }


def local_connector_answers(turn: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in when the SDK/key is absent.

    Keyword rules only — never mints a tool outside the closed catalog and
    never copies digits out of the utterance.
    """
    text = str((turn or {}).get("utterance") or "").lower()
    pad = _has_any(text, _PAD_WORDS)
    publish = _has_any(text, _PUBLISH_WORDS)
    offbox = _has_any(text, _OFFBOX_WORDS)
    digits = _has_any(text, _DIGIT_WORDS)
    asserts = bool(_SCORE_ASSERT_RE.search(text)) or "score is" in text
    pack = _has_any(text, _PACK_WORDS)
    clip = _has_any(text, _CLIP_WORDS)
    timeline = _has_any(text, _TIMELINE_WORDS)
    live = _has_any(text, _LIVE_WORDS) or digits

    if pad:
        tool = "refuse_actuator"
    elif publish:
        tool = "refuse_mid_drive_publish"
    elif pack:
        tool = "export_presence_pack"
    elif clip:
        tool = "request_licensed_clip"
    elif timeline:
        tool = "get_timeline"
    elif live:
        tool = "get_observation"
    else:
        tool = "silent"

    needs_tool = tool != "silent"
    risk = RISK_ACTUATOR_OR_EXFIL if (pad or publish) else (1 if digits or clip else 0)
    return {
        "tool": tool,
        "tool_confidence": 0.85 if needs_tool else 0.2,
        "request_risk": risk,
        "nouls": {
            "asks_for_digits": 0.9 if digits else 0.0,
            "asks_to_control_pad": 0.9 if pad else 0.0,
            "asks_to_publish_now": 0.9 if publish else 0.0,
            "asks_to_leave_localhost": 0.8 if offbox else 0.0,
            "asserts_a_score": 0.9 if asserts else 0.0,
            "needs_a_tool_at_all": 0.9 if needs_tool else 0.1,
            "wants_heat": 0.8 if _has_any(text, _HEAT_WORDS) else 0.0,
        },
        "source": "local_heuristic",
    }


def _preflight_deny(turn: dict[str, Any]) -> str | None:
    """Deterministic refuses before classification (actuator / wrap)."""
    if not isinstance(turn, dict):
        return "actuator_or_exfil"
    if turn.get("pad_command") or turn.get("actuator") or turn.get("dualsense"):
        return "pad_not_on_this_plane"
    dest = str(turn.get("wrap_dest") or turn.get("dest_plane") or "").strip()
    if dest and dest not in _ALLOWED_WRAP_DESTS:
        return "off_plane_wrap"
    return None


def compose_bind(
    *,
    agent: dict[str, Any],
    intent: dict[str, Any],
    observatory: dict[str, Any],
    session_id: str = "",
    source: str = "local_heuristic",
    forced_deny: str | None = None,
    seq_match_window: int = DEFAULT_SEQ_MATCH_WINDOW,
    turn: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Code-owned compose. The model classified; Python decides.

    Deny order follows OCCF "TypeSafe door": pad -> mid-drive publish ->
    leave-localhost -> silent band -> risk=actuator. Synchronization is
    first-match over live_pull -> seq_match -> chapter_id -> recap_door.
    """
    turn = turn if isinstance(turn, dict) else {}
    obs = normalize_observatory(observatory)
    intent = intent if isinstance(intent, dict) else {}
    tool = _norm_tool(intent.get("tool"))
    nouls_in = intent.get("nouls") if isinstance(intent.get("nouls"), dict) else {}
    nouls = {n: _f(nouls_in.get(n)) for n in NOULS}
    wants_heat = _f(nouls_in.get("wants_heat"))
    tool_conf = intent.get("tool_confidence")
    tool_conf = _f(tool_conf) if tool_conf is not None else None
    risk = int(_f(intent.get("request_risk")))
    risk = max(0, min(2, risk))

    live = bool(obs["live"])
    climax_ready = bool(obs["climax_ready"])
    last_confirm = obs["last_confirm"]

    # ── compose denies (code-owned, OCCF order; silent band before risk) ──
    deny_reason = forced_deny if forced_deny in DENY_REASONS else None
    if deny_reason is None:
        if nouls["asks_to_control_pad"] >= NOUL_DENY or tool == "refuse_actuator":
            deny_reason = "pad_not_on_this_plane"
        elif tool == "refuse_mid_drive_publish" or (
            nouls["asks_to_publish_now"] >= NOUL_DENY and live and not climax_ready
        ):
            deny_reason = "mid_drive"
        elif nouls["asks_to_leave_localhost"] >= NOUL_DENY and not obs["lan_opt_in"]:
            deny_reason = "localhost_only"

    silent = (
        deny_reason is None
        and (
            tool == "silent"
            or (tool_conf is not None and tool_conf < TOOL_CONF_MIN)
            or nouls["needs_a_tool_at_all"] < NEEDS_TOOL_MIN
        )
    )
    if deny_reason is None and not silent and risk == RISK_ACTUATOR_OR_EXFIL:
        deny_reason = "actuator_or_exfil"

    # ── synchronization: first match wins, no interpolation ──
    method = "none"
    same_seq: bool | None = None
    witness_hash: Any = None
    bound = False

    if deny_reason is None and not silent:
        echo_seq = _num(
            turn.get("echo_frame_seq")
            if turn.get("echo_frame_seq") is not None
            else turn.get("frame_seq")
        )
        chapter_id = str(turn.get("chapter_id") or "").strip()
        if tool == "get_observation" and live and obs["has_frame"]:
            method = "live_pull"
            bound = True
            same_seq = True
            witness_hash = obs["witness_hash"] or obs["crop_hash"]
        elif echo_seq is not None:
            method = "seq_match"
            cur = obs["frame_seq"]
            lo, hi = obs["seq_lo"], obs["seq_hi"]
            in_window = (
                (cur is not None and abs(cur - echo_seq) <= int(seq_match_window))
                or (lo is not None and hi is not None and lo <= echo_seq <= hi)
            )
            same_seq = cur is not None and echo_seq == cur
            if in_window:
                bound = True
                seq_clocks = obs["seq_clocks"]
                witness_hash = obs["witness_hash"] or f"seq:{echo_seq}"
                if not same_seq:
                    # The echoed seq names its own instant, if known.
                    obs["clock_ns"] = int(_num(seq_clocks.get(echo_seq)) or 0)
                    obs["frame_seq"] = echo_seq
            else:
                bound = False  # stale below
        elif chapter_id:
            ch = obs["chapters"].get(chapter_id)
            if isinstance(ch, dict):
                method = "chapter_id"
                bound = True
                obs["clock_ns"] = int(_num(ch.get("t0_clock_ns")) or 0)
                obs["frame_seq"] = _num(ch.get("frame_seq"))
                witness_hash = ch.get("witness_hash") or f"chapter:{chapter_id}"
        elif obs["recap_open"] or obs["recap_clock_commitment"] is not None:
            method = "recap_door"
            bound = True
            obs["clock_ns"] = int(obs["recap_clock_commitment"] or 0)
            witness_hash = obs["recap_witness_hash"] or "recap_door"

    # ── correlation state ──
    if deny_reason is not None:
        state = "denied"
        method = "none"
        witness_hash = None
    elif silent or not bound:
        if method == "seq_match" and not silent:
            state = "stale"  # echoed seq fell out of window
        else:
            state = "unbound"
            if method not in SYNC_METHODS:
                method = "none"
    elif obs["ticket_stale"] and last_confirm == "present" and method in (
        "live_pull",
        "seq_match",
    ):
        state = "stale"  # confirm present but crop/seq drifted (ticket_stale)
    else:
        state = "bound"

    # ── compose action + speech license ──
    digit_ask = (
        nouls["asks_for_digits"] >= NOUL_SOFT
        or nouls["asserts_a_score"] >= NOUL_SOFT
    )
    if state == "denied":
        action, speech = "deny", "none"
    elif state == "unbound" and silent:
        action, speech = "silent", "none"
    elif state == "stale":
        action, speech = "watch", "boxes"  # drift token; digits stay boxed
    else:
        action = "act"
        if digit_ask:
            speech = (
                "confirm_tokens"
                if (state == "bound" and last_confirm == "present")
                else "boxes"
            )
        elif wants_heat >= NOUL_SOFT and obs["coupling"] == "present" and state == "bound":
            speech = "heat"
        else:
            speech = "none"

    return {
        "schema": SCHEMA,
        "plane": PLANE,
        "licenses_digits": False,
        "bind_id": f"cb-{uuid.uuid4().hex[:12]}",
        "session_id": str(session_id or ""),
        "agent": {
            "brand": _norm_brand(agent.get("brand") if isinstance(agent, dict) else None),
            "turn_id": str((agent or {}).get("turn_id") or ""),
            "asked_at_unix_ms": _num((agent or {}).get("asked_at_unix_ms")) or 0,
        },
        "observatory": {
            "clock_ns": obs["clock_ns"],
            "frame_seq": obs["frame_seq"],
            "crop_hash": obs["crop_hash"],
            "title_lock": obs["title_lock"],
            "board_lock": obs["board_lock"],
            "last_confirm": obs["last_confirm"],
            "coupling": obs["coupling"],
            "climax_ready": obs["climax_ready"],
            "live": obs["live"],
        },
        "intent": {
            "tool": tool,
            "tool_confidence": tool_conf,
            "request_risk": risk,
            "nouls": {**nouls, "wants_heat": wants_heat},
        },
        "compose": {
            "action": action,
            "deny_reason": deny_reason,
            "speech": speech,
        },
        "correlation": {
            "state": state,
            "method": method if method in SYNC_METHODS else "none",
            "same_seq": same_seq,
            "witness_hash": witness_hash,
        },
        "source": source if source in SOURCES else "local_heuristic",
    }


class ConnectorBind:
    """OCCF ingress engine. Synchronous, pull-only; no bus, no worker.

    ``bind_turn`` composes one ``qoresence.connector-bind.v0`` row per agent
    turn and notes it on the unified Jev ledger as ``pack="connector"`` —
    accept and refuse alike. Never writes a private connector.jsonl.
    """

    def __init__(self, config: Any = None, *, ask_fn: Any = None) -> None:
        self.config = config
        self._ask_fn = ask_fn
        self.enabled = (
            bool(getattr(config, "enabled", False)) if config is not None else False
        ) or _env_enabled()
        self._seq_match_window = int(
            getattr(config, "seq_match_window", DEFAULT_SEQ_MATCH_WINDOW)
            or DEFAULT_SEQ_MATCH_WINDOW
        )
        self._typesafe_timeout_s = float(
            getattr(config, "typesafe_timeout_s", DEFAULT_TIMEOUT_S)
            or DEFAULT_TIMEOUT_S
        )
        self._warned_typesafe = [False]
        self._lock = threading.Lock()
        self._binds = 0
        self._asked = 0
        self._states = {s: 0 for s in CORRELATION_STATES}
        self._last: dict[str, Any] = {}
        if self.enabled:
            try:
                # The connector flag implies a ledger write for these rows:
                # binds exist only as pack="connector" judgments.
                configure_jev_ledger(enabled=True)
            except Exception as e:
                log.debug("connector ledger ensure skipped: %s", e)

    def _classify(self, turn: dict[str, Any], obs: dict[str, Any]) -> dict[str, Any]:
        answers = None
        state = {
            "policy": (
                "Observation only. Classify the agent ask; never mint digits, "
                "never drive the pad, never publish mid-drive."
            ),
            "agent": normalize_agent(turn),
            "turn": {
                "utterance": str(turn.get("utterance") or "")[:2000],
                "echo_frame_seq": _num(turn.get("echo_frame_seq")),
                "chapter_id": str(turn.get("chapter_id") or "")[:200],
            },
            "observatory": {
                "live": obs["live"],
                "title_lock": obs["title_lock"],
                "board_lock": obs["board_lock"],
                "last_confirm": obs["last_confirm"],
                "coupling": obs["coupling"],
                "climax_ready": obs["climax_ready"],
            },
        }
        if self._ask_fn is not None:
            try:
                answers = self._ask_fn(state)
            except Exception:
                answers = None
        if answers is None:
            answers = self._try_typesafe(state)
        if answers is None:
            answers = local_connector_answers(turn)
        return answers

    def _try_typesafe(self, state: dict[str, Any]) -> dict[str, Any] | None:
        questions = connector_bind_questions()
        if not questions:
            return None
        response = system_one(
            state=state,
            questions=questions,
            timeout_s=self._typesafe_timeout_s,
            warn_label="connector_bind",
            warned_flag=self._warned_typesafe,
            logger=log,
        )
        if response is None:
            return None
        self._asked += 1
        choices = getattr(response, "choices", {}) or {}
        nouls_r = getattr(response, "nouls", {}) or {}
        scores = getattr(response, "scores", {}) or {}
        tc = choices.get("tool")
        rr = scores.get("request_risk")

        def _n(name: str) -> float:
            obj = nouls_r.get(name)
            try:
                return float(obj.noul) if obj is not None else 0.0
            except Exception:
                return 0.0

        return {
            "tool": getattr(tc, "choice", None) if tc is not None else None,
            "tool_confidence": (
                float(getattr(tc, "confidence", 0) or 0) if tc is not None else None
            ),
            "request_risk": int(float(rr.score)) if rr is not None else 0,
            "nouls": {n: _n(n) for n in NOULS},
            "source": "typesafe",
        }

    def bind_turn(
        self,
        turn: dict[str, Any],
        *,
        observatory: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Compose one bind row for an agent turn; note it on the ledger.

        Returns the bind dict (or None when the connector is off). Rows are
        written only when a session_id exists — ingress on AND a session.
        """
        if not self.enabled or not isinstance(turn, dict):
            return None
        obs = normalize_observatory(observatory or turn.get("observatory"))
        sid = session_id or turn.get("session_id") or obs.get("session_id") or ""
        agent = normalize_agent(turn)
        forced = _preflight_deny(turn)
        if forced is not None:
            intent = {
                "tool": _norm_tool(turn.get("tool")),
                "tool_confidence": None,
                "request_risk": RISK_ACTUATOR_OR_EXFIL,
                "nouls": {},
            }
            source = "preflight"
        else:
            intent = self._classify(turn, obs)
            source = str(intent.get("source") or "local_heuristic")
        bind = compose_bind(
            agent=agent,
            intent=intent,
            observatory=obs,
            session_id=str(sid),
            source=source,
            forced_deny=forced,
            seq_match_window=self._seq_match_window,
            turn=turn,
        )
        if sid:
            note_judgment(
                "connector",
                bind,
                clock_ns=bind["observatory"]["clock_ns"],
                frame_seq=bind["observatory"]["frame_seq"],
            )
        with self._lock:
            self._binds += 1
            st = str(bind["correlation"]["state"])
            if st in self._states:
                self._states[st] += 1
            self._last = bind
        return bind

    def last(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            states = dict(self._states)
            last = dict(self._last)
        return {
            "enabled": bool(self.enabled),
            "key_present": key_present(),
            "binds": self._binds,
            "states": states,
            "asked": self._asked,
            "last_state": (last.get("correlation") or {}).get("state"),
            "last_source": last.get("source"),
            "licenses_digits": False,
        }

    def stop(self) -> None:
        """No worker, no bus subscription — present for pack symmetry."""
        return


_singleton: ConnectorBind | None = None
_singleton_lock = threading.Lock()


def get_connector_bind() -> ConnectorBind | None:
    with _singleton_lock:
        return _singleton


def make_connector_from_config(
    config: Any,
    *,
    ask_fn: Any = None,
) -> ConnectorBind | None:
    enabled = (
        bool(getattr(config, "enabled", False)) if config is not None else False
    ) or _env_enabled()
    if not enabled:
        return None
    eng = ConnectorBind(config, ask_fn=ask_fn)
    if not eng.enabled:
        return None
    global _singleton
    with _singleton_lock:
        _singleton = eng
    return eng


def reset_connector_bind() -> None:
    """Clear the singleton. Tests and shutdown only."""
    global _singleton
    with _singleton_lock:
        _singleton = None


def note_agent_turn(
    turn: dict[str, Any],
    *,
    observatory: dict[str, Any] | None = None,
    session_id: str | None = None,
) -> dict[str, Any] | None:
    """Module-level ingress used by later MCP / skill scaffolding.

    Returns None when the connector is off — the caller treats that as
    "no bind existed" and simply serves the read as usual.
    """
    eng = get_connector_bind()
    if eng is None:
        return None
    return eng.bind_turn(turn, observatory=observatory, session_id=session_id)
