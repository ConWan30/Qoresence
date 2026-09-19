"""Mint verifier — Jev judgment pack for hold / remint / blank / observe.

Second clock over evidence on the confirm path. Code still owns ConfirmTicket,
SEQGATE, and digit paint. Jev never mints scores.

Same shape as ticket_stale / Noul observatory (AGENTS.md Rules 5–6):

1. ``_on_event`` only enqueues (bounded, drop-oldest). Never blocks, never
   emits, never acquires a lobe lock.
2. A daemon worker on a cadence timer judges ``ticket`` vs ``live`` via
   TypeSafe, falling back to a deterministic local heuristic when the SDK/key
   is absent.
3. ``licenses_digits`` is False forever. v0 ``action`` is advisory speech;
   remint actuation is a later flag.

Opt-in: ``--mint-verifier`` / ``QORESENCE_MINT_VERIFIER=1``, or under the
Jev umbrella ``--jev`` / ``QORESENCE_JEV=1``. ``--play`` does not enable.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

from qoresence.observability.mint_verifier_questions import (
    ACTIONS,
    BLANK_HUD,
    CONF_ACT,
    CONF_SOFT,
    DETERMINISTIC_REFUSE,
    HUD_KINDS,
    mint_verifier_questions,
)
from qoresence.observability.typesafe_ask import (
    DEFAULT_TIMEOUT_S,
    system_one,
)

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_MINT_VERIFIER", "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    } or os.environ.get("QORESENCE_JEV", "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }


def _key_present() -> bool:
    if os.environ.get("TYPESAFE_API_KEY", "").strip():
        return True
    try:
        p = Path(".secrets/typesafe.key")
        return p.is_file() and bool(p.stat().st_size)
    except Exception:
        return False


def _norm_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _norm_team(v: Any) -> str:
    return str(v or "").strip().upper()


def compose_mint_verdict(
    *,
    same_game: float | None = None,
    scorebug_in_crop: float | None = None,
    pair_matches_ticket: float | None = None,
    legal_transition: float | None = None,
    hud_kind: str | None = None,
    hud_confidence: float | None = None,
    has_ticket: bool = False,
    gate_reason: str | None = None,
    pair_differs: bool | None = None,
) -> dict[str, Any]:
    """Code-owned policy. Noul probability is the gate (no separate confidence).

    ``action`` is advisory in v0. Deterministic refuse cannot be talked down.
    Empty ticks (no scorebug in crop) observe — they do not remint.
    """
    kind = hud_kind if hud_kind in HUD_KINDS else "unknown"
    h_conf = float(hud_confidence or 0.0)
    sg = same_game
    sc = scorebug_in_crop
    pm = pair_matches_ticket
    lt = legal_transition
    differs = bool(pair_differs)

    if not has_ticket:
        action = "observe"
    elif str(gate_reason or "") in DETERMINISTIC_REFUSE:
        action = "blank"
    elif kind in BLANK_HUD and h_conf >= CONF_SOFT:
        action = "blank"
    elif sg is not None and sg <= 0.3:
        action = "blank"
    elif (
        sc is not None
        and sc >= CONF_ACT
        and pm is not None
        and pm >= CONF_ACT
    ):
        action = "hold"
    elif (
        sc is not None
        and sc >= CONF_ACT
        and pm is not None
        and pm <= 0.3
        and differs
        and lt is not None
        and lt >= CONF_ACT
    ):
        action = "remint"
    elif sc is not None and sc <= 0.3:
        action = "observe"
    else:
        action = "observe"
    if action not in ACTIONS:
        action = "observe"

    return {
        "plane": PLANE,
        "action": action,
        "hud_kind": kind,
        "hud_confidence": round(h_conf, 3),
        "same_game": sg,
        "scorebug_in_crop": sc,
        "pair_matches_ticket": pm,
        "legal_transition": lt if differs else None,
        "gate_reason": gate_reason,
        "licenses_digits": False,
    }


def local_mint_answers(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in when the SDK/key is absent."""
    ticket = state.get("ticket") if isinstance(state.get("ticket"), dict) else {}
    live = state.get("live") if isinstance(state.get("live"), dict) else {}

    t_hs, t_aws = _norm_int(ticket.get("home_score")), _norm_int(ticket.get("away_score"))
    l_hs, l_aws = _norm_int(live.get("home_score")), _norm_int(live.get("away_score"))
    t_ht, t_at = _norm_team(ticket.get("home_team")), _norm_team(ticket.get("away_team"))
    l_ht, l_at = _norm_team(live.get("home_team")), _norm_team(live.get("away_team"))
    live_has_board = l_hs is not None and l_aws is not None
    hud = str(live.get("hud_kind") or "").strip() or None
    if hud not in HUD_KINDS:
        if not live_has_board:
            hud = "no_board"
        elif hud in BLANK_HUD:
            pass
        else:
            hud = "live_hud"

    teams_live = bool(l_ht or l_at)
    teams_ticket = bool(t_ht or t_at)
    if teams_live and teams_ticket and (l_ht, l_at) != (t_ht, t_at):
        same_game = 0.15
    elif teams_live and teams_ticket:
        same_game = 0.85
    else:
        same_game = 0.7

    if hud in BLANK_HUD or hud == "no_board" or not live_has_board:
        scorebug = 0.1
    else:
        scorebug = 0.8

    pair_differs = (
        live_has_board
        and t_hs is not None
        and t_aws is not None
        and (l_hs, l_aws) != (t_hs, t_aws)
    )
    if live_has_board and t_hs is not None and (l_hs, l_aws) == (t_hs, t_aws):
        pair_matches = 0.9
    else:
        pair_matches = 0.1

    legal = 0.1
    if pair_differs:
        try:
            from qoresence.sync.digit_integrity import implausible_transition_reason

            reason = implausible_transition_reason(t_hs, t_aws, l_hs, l_aws)
            legal = 0.1 if reason else 0.85
        except Exception:
            legal = 0.1

    return {
        "same_game": same_game,
        "scorebug_in_crop": scorebug,
        "pair_matches_ticket": pair_matches,
        "legal_transition": legal,
        "hud_kind": hud,
        "hud_confidence": 0.85,
        "pair_differs": pair_differs,
        "source": "local_heuristic",
    }


class MintVerifierSentinel:
    """Enqueue-only bus subscriber + timer worker. Never on the capture path."""

    def __init__(
        self,
        config: Any = None,
        *,
        bus: Any = None,
        ask_fn: Any = None,
        ticket_fn: Any = None,
        live_fn: Any = None,
    ) -> None:
        self.config = config
        self._bus = bus
        self._ask_fn = ask_fn
        self._ticket_fn = ticket_fn
        self._live_fn = live_fn
        self._lock = threading.Lock()
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(
            maxsize=int(getattr(config, "queue_size", 256) or 256)
        )
        self._dropped = 0
        self._ticks = 0
        self._judged = 0
        self._asked = 0
        self._last: dict[str, Any] = {}
        self._last_ns = 0
        self._latest_live: dict[str, Any] = {}
        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None
        self._unsubscribe: Any = None
        self._jsonl_handle: Any = None
        self._cadence_s = float(getattr(config, "cadence_s", 2.0) or 2.0)
        enabled = bool(getattr(config, "enabled", False)) if config is not None else False
        self.enabled = enabled or _env_enabled()
        self._warned_typesafe = [False]
        timeout = DEFAULT_TIMEOUT_S
        if config is not None:
            timeout = float(getattr(config, "typesafe_timeout_s", DEFAULT_TIMEOUT_S) or DEFAULT_TIMEOUT_S)
        self._typesafe_timeout_s = timeout
        if not self.enabled:
            return
        out_dir = Path(getattr(config, "out_dir", "logs/mint_verifier") or "logs/mint_verifier")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            self._jsonl_handle = (out_dir / "mint_verifier.jsonl").open("a", encoding="utf-8")
        except Exception as e:
            log.debug("mint_verifier jsonl not opened: %s", e)
        if bus is not None:
            try:
                self._unsubscribe = bus.subscribe_raw(self._on_event)
            except Exception:
                try:
                    self._unsubscribe = bus.subscribe(self._on_event)
                except Exception as e:
                    log.debug("mint_verifier bus subscribe skipped: %s", e)
        self._worker = threading.Thread(
            target=self._run, name="mint-verifier", daemon=True
        )
        self._worker.start()

    def _on_event(self, ev: Any) -> None:
        if not self.enabled:
            return
        try:
            payload = getattr(ev, "payload", None)
            if not isinstance(payload, dict):
                return
            parsed = payload.get("parsed") or payload.get("vlm") or payload.get("last")
            if parsed is not None and not isinstance(parsed, dict):
                parsed = None
            rec = {
                "clock_ns": int(getattr(ev, "clock_ns", 0) or payload.get("clock_ns") or 0),
                "parsed": parsed,
                "crop_hash": payload.get("crop_hash"),
                "vlm_status": payload.get("vlm_status"),
                "last_reason": payload.get("last_reason") or payload.get("reason"),
            }
            if rec["parsed"] is None and not rec["crop_hash"]:
                return
            try:
                self._queue.put_nowait(rec)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                self._dropped += 1
                try:
                    self._queue.put_nowait(rec)
                except queue.Full:
                    self._dropped += 1
        except Exception:
            return

    def _ticket_state(self) -> dict[str, Any]:
        if self._ticket_fn is not None:
            try:
                t = self._ticket_fn()
                return dict(t) if isinstance(t, dict) else {}
            except Exception:
                return {}
        try:
            from qoresence.vision.confirm_ticket import licensed_last_confirm

            last = licensed_last_confirm()
            if last is None:
                return {"has_ticket": False}
            out = last.to_dict() if hasattr(last, "to_dict") else {}
            if not out:
                out = {
                    "home_score": getattr(last, "home_score", None),
                    "away_score": getattr(last, "away_score", None),
                    "home_team": getattr(last, "home_team", None),
                    "away_team": getattr(last, "away_team", None),
                    "quarter": getattr(last, "quarter", None),
                    "down": getattr(last, "down", None),
                    "clock_ns": getattr(last, "clock_ns", None),
                }
            out["has_ticket"] = True
            return out
        except Exception:
            return {"has_ticket": False}

    def _drain_live(self) -> None:
        while True:
            try:
                rec = self._queue.get_nowait()
            except queue.Empty:
                return
            parsed = rec.get("parsed") if isinstance(rec.get("parsed"), dict) else {}
            live = {
                "clock_ns": rec.get("clock_ns"),
                "crop_hash": rec.get("crop_hash") or parsed.get("crop_hash"),
                "home_score": parsed.get("home_score"),
                "away_score": parsed.get("away_score"),
                "home_team": parsed.get("home_team") or parsed.get("left_team"),
                "away_team": parsed.get("away_team") or parsed.get("right_team"),
                "quarter": parsed.get("quarter"),
                "down": parsed.get("down"),
                "vlm_status": rec.get("vlm_status") or parsed.get("vlm_status"),
                "last_reason": rec.get("last_reason"),
            }
            with self._lock:
                self._latest_live = live

    def _noul_hud_kind(self) -> str | None:
        try:
            from qoresence.observability.noul_observatory import get_noul_observatory

            noul = get_noul_observatory()
            if noul is None:
                return None
            stats = noul.stats() if hasattr(noul, "stats") else {}
            kind = stats.get("hud_kind")
            return kind if kind in HUD_KINDS else None
        except Exception:
            return None

    def _live_state(self) -> dict[str, Any]:
        if self._live_fn is not None:
            try:
                v = self._live_fn()
                if isinstance(v, dict):
                    return dict(v)
            except Exception:
                pass
        self._drain_live()
        with self._lock:
            live = dict(self._latest_live)
        if not live:
            try:
                from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

                last = get_scoreboard_vlm().get_last()
                live = dict(last) if isinstance(last, dict) else {}
            except Exception:
                live = {}
        if "hud_kind" not in live or not live.get("hud_kind"):
            kind = self._noul_hud_kind()
            if kind:
                live["hud_kind"] = kind
        return live

    def _judge(self, state: dict[str, Any]) -> dict[str, Any]:
        answers = None
        if self._ask_fn is not None:
            answers = self._ask_fn(state)
        if answers is None:
            answers = self._try_typesafe(state)
        if answers is None:
            answers = local_mint_answers(state)
        ticket = state.get("ticket") if isinstance(state.get("ticket"), dict) else {}
        verdict = compose_mint_verdict(
            same_game=answers.get("same_game"),
            scorebug_in_crop=answers.get("scorebug_in_crop"),
            pair_matches_ticket=answers.get("pair_matches_ticket"),
            legal_transition=answers.get("legal_transition"),
            hud_kind=answers.get("hud_kind"),
            hud_confidence=answers.get("hud_confidence"),
            has_ticket=bool(ticket.get("has_ticket") or ticket.get("home_score") is not None),
            gate_reason=state.get("gate_reason"),
            pair_differs=answers.get("pair_differs"),
        )
        verdict["source"] = answers.get("source") or "unknown"
        return verdict

    def _try_typesafe(self, state: dict[str, Any]) -> dict[str, Any] | None:
        questions = mint_verifier_questions()
        if not questions:
            return None
        ticket = state.get("ticket") if isinstance(state.get("ticket"), dict) else {}
        live = state.get("live") if isinstance(state.get("live"), dict) else {}
        t_hs, t_aws = _norm_int(ticket.get("home_score")), _norm_int(ticket.get("away_score"))
        l_hs, l_aws = _norm_int(live.get("home_score")), _norm_int(live.get("away_score"))
        pair_differs = (
            t_hs is not None
            and t_aws is not None
            and l_hs is not None
            and l_aws is not None
            and (l_hs, l_aws) != (t_hs, t_aws)
        )
        payload = {
            "policy": {
                "never_mint": True,
                "football_deltas": [1, 2, 3, 6, 7, 8],
            },
            "ticket": {
                "has_ticket": bool(ticket.get("has_ticket") or t_hs is not None),
                "home_score": t_hs,
                "away_score": t_aws,
                "home_team": ticket.get("home_team"),
                "away_team": ticket.get("away_team"),
                "quarter": ticket.get("quarter"),
                "down": ticket.get("down"),
                "age_s": ticket.get("age_s"),
            },
            "live": {
                "home_score": l_hs,
                "away_score": l_aws,
                "home_team": live.get("home_team"),
                "away_team": live.get("away_team"),
                "quarter": live.get("quarter"),
                "down": live.get("down"),
                "vlm_status": live.get("vlm_status"),
                "last_reason": live.get("last_reason"),
                "hud_kind": live.get("hud_kind"),
                "recheck_status": live.get("recheck_status"),
                "gate_reason": state.get("gate_reason"),
            },
        }
        response = system_one(
            state=payload,
            questions=questions,
            timeout_s=self._typesafe_timeout_s,
            warn_label="mint_verifier",
            warned_flag=self._warned_typesafe,
            logger=log,
        )
        if response is None:
            return None
        self._asked += 1
        nouls = getattr(response, "nouls", {}) or {}
        choices = getattr(response, "choices", {}) or {}
        hk = choices.get("hud_kind")

        def _noul(name: str) -> float | None:
            obj = nouls.get(name)
            if obj is None:
                return None
            try:
                return float(obj.noul)
            except Exception:
                return None

        return {
            "same_game": _noul("same_game"),
            "scorebug_in_crop": _noul("scorebug_in_crop"),
            "pair_matches_ticket": _noul("pair_matches_ticket"),
            "legal_transition": _noul("legal_transition"),
            "hud_kind": getattr(hk, "choice", None) if hk is not None else None,
            "hud_confidence": (
                float(getattr(hk, "confidence", 0) or 0) if hk is not None else None
            ),
            "pair_differs": pair_differs,
            "source": "typesafe",
        }

    def _run(self) -> None:
        while not self._stop_evt.wait(self._cadence_s):
            try:
                ticket = self._ticket_state()
                live = self._live_state()
                state = {
                    "ticket": ticket,
                    "live": live,
                    "gate_reason": live.get("gate_reason") or ticket.get("gate_reason"),
                }
                verdict = self._judge(state)
                verdict["tick"] = self._ticks
                verdict["ts"] = time.time()
                with self._lock:
                    self._last = verdict
                    self._last_ns = time.monotonic_ns()
                    self._ticks += 1
                    self._judged += 1
                self._write_jsonl(verdict)
            except Exception as e:
                log.debug("mint_verifier tick failed: %s", e)

    def _write_jsonl(self, row: dict[str, Any]) -> None:
        handle = self._jsonl_handle
        if handle is None:
            return
        try:
            safe = {
                k: v
                for k, v in row.items()
                if k not in {"ticket_id", "confirm_ticket_id"}
            }
            handle.write(json.dumps(safe, separators=(",", ":"), default=str) + "\n")
            handle.flush()
        except Exception:
            pass

    def last(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            last = dict(self._last)
            ticks, judged, dropped, asked = (
                self._ticks,
                self._judged,
                self._dropped,
                self._asked,
            )
            last_ns = self._last_ns
        age = None
        if last_ns:
            age = round((time.monotonic_ns() - last_ns) / 1e9, 3)
        return {
            "enabled": bool(self.enabled),
            "key_present": _key_present(),
            "ticks": ticks,
            "judged": judged,
            "asked": asked,
            "dropped": dropped,
            "last_age_s": age,
            "action": last.get("action"),
            "hud_kind": last.get("hud_kind"),
            "same_game": last.get("same_game"),
            "scorebug_in_crop": last.get("scorebug_in_crop"),
            "pair_matches_ticket": last.get("pair_matches_ticket"),
            "legal_transition": last.get("legal_transition"),
            "source": last.get("source"),
            "licenses_digits": False,
        }

    def stop(self) -> None:
        self._stop_evt.set()
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            except Exception:
                pass
            self._unsubscribe = None
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=2.0)
        if self._jsonl_handle is not None:
            try:
                self._jsonl_handle.close()
            except Exception:
                pass
            self._jsonl_handle = None


_singleton: MintVerifierSentinel | None = None
_singleton_lock = threading.Lock()


def get_mint_verifier() -> MintVerifierSentinel | None:
    with _singleton_lock:
        return _singleton


def make_mint_verifier_from_config(
    config: Any,
    *,
    bus: Any = None,
    jev_enabled: bool = False,
    ask_fn: Any = None,
) -> MintVerifierSentinel | None:
    enabled = bool(getattr(config, "enabled", False)) or jev_enabled or _env_enabled()
    if not enabled:
        return None
    cfg = config
    if jev_enabled and not bool(getattr(config, "enabled", False)):
        try:
            from dataclasses import replace

            from qoresence.core.unified_config import MintVerifierConfig

            cfg = replace(
                config if config is not None else MintVerifierConfig(),
                enabled=True,
            )
        except Exception:
            cfg = config
    sen = MintVerifierSentinel(cfg, bus=bus, ask_fn=ask_fn)
    if not sen.enabled:
        return None
    global _singleton
    with _singleton_lock:
        _singleton = sen
    return sen
