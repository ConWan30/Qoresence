"""Ticket-stale sentinel — Jev judgment pack for live-board stuck locks.

The stuck-lock class: a confirm ticket still licenses old-match digits while
the VLM crop / live board has moved on (new HUD state, menu plate, different
matchup, or an aging ticket clock). SEQGATE / digit_integrity already blanks
deterministically; this pack is the *semantic observer* that names the drift
and records it to JSONL for audit.

Same shape as the Noul observatory / SyncCoroner (AGENTS.md Rules 5–6 class):

1. ``_on_event`` only enqueues (bounded, drop-oldest). Never blocks, never
   emits, never acquires a lobe lock.
2. A daemon worker on a cadence timer judges ``ticket`` vs ``live`` state via
   TypeSafe, falling back to a deterministic local heuristic when the SDK/key
   is absent.
3. ``licenses_digits`` is False forever: never mints scores, never blanks the
   board itself — ``action`` is advisory audit only.

Opt-in: ``--jev-ticket-stale`` / ``QORESENCE_JEV_TICKET_STALE=1``, or under the
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

from qoresence.observability.ticket_stale_questions import (
    CONF_ACT,
    CONF_SOFT,
    STALE_AFTER_NS,
    STALE_CLASSES,
    ticket_stale_questions,
)
from qoresence.observability.typesafe_ask import (
    DEFAULT_TIMEOUT_S,
    system_one,
)

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"

_EVENT_TYPES = frozenset({"visual", "scoreboard", "router_decision", "presence_report"})


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_JEV_TICKET_STALE", "").strip().lower() in {
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


def compose_stale_verdict(
    *,
    stale_class: str | None = None,
    stale_confidence: float | None = None,
    hold_noul: float | None = None,
    freshness: float | None = None,
    gate_reason: str | None = None,
) -> dict[str, Any]:
    """Code-owned policy. Confidence bands: >=0.7 act / 0.4-0.7 soft / <0.4 observe.

    ``action`` is advisory only — SEQGATE/digit_integrity own the real blank.
    ``gate_reason`` echoes the deterministic SEQGATE reason for cross-checking;
    a deterministic ticket_stale/crop_mismatch can never be talked down to
    "fresh" by the model.
    """
    cls = stale_class if stale_class in STALE_CLASSES else "unknown"
    conf = float(stale_confidence or 0.0)
    noul = hold_noul
    fresh = float(freshness) if freshness is not None else None

    deterministic_stale = gate_reason in {"ticket_stale", "crop_mismatch", "seq_skew"}
    stale_model = cls in {"crop_moved_on", "match_changed", "menu_or_plate"} or (
        cls == "clock_drift" and conf >= CONF_SOFT
    )
    hold_yes = noul is not None and noul >= CONF_ACT
    hold_soft = noul is not None and CONF_SOFT <= noul < CONF_ACT
    stale_low_fresh = fresh is not None and fresh <= 0.5

    if deterministic_stale or (hold_yes and conf >= CONF_ACT and stale_model):
        action = "flag_stale"
    elif (stale_model and conf >= CONF_SOFT) or hold_soft or stale_low_fresh:
        action = "watch"
    else:
        action = "observe"
    if deterministic_stale and cls in {"fresh", "unknown"}:
        cls = "crop_moved_on" if gate_reason == "crop_mismatch" else "clock_drift"

    return {
        "plane": PLANE,
        "stale_class": cls,
        "stale_confidence": round(conf, 3),
        "hold_noul": noul,
        "freshness": fresh,
        "gate_reason": gate_reason,
        "action": action,
        "licenses_digits": False,
    }


def local_stale_answers(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in when the SDK/key is absent.

    Mirrors digit_integrity in judgment form — not a second license path.
    """
    ticket = state.get("ticket") if isinstance(state.get("ticket"), dict) else {}
    live = state.get("live") if isinstance(state.get("live"), dict) else {}
    gate_reason = str(state.get("gate_reason") or "")

    t_hs, t_aws = _norm_int(ticket.get("home_score")), _norm_int(ticket.get("away_score"))
    l_hs, l_aws = _norm_int(live.get("home_score")), _norm_int(live.get("away_score"))
    t_crop = str(ticket.get("crop_hash") or "").strip()
    l_crop = str(live.get("crop_hash") or "").strip()
    t_clk = int(ticket.get("clock_ns") or 0)
    l_clk = int(live.get("clock_ns") or 0)
    age_ns = max(0, l_clk - t_clk) if t_clk and l_clk else 0
    live_paused = bool(live.get("paused"))
    live_has_board = l_hs is not None and l_aws is not None
    identity_stale = bool(state.get("identity_stale"))

    if not ticket:
        cls, conf, noul, fresh = "unknown", 0.85, 0.1, None
    elif identity_stale or gate_reason == "crop_mismatch" or (l_crop and t_crop and l_crop != t_crop):
        cls, conf, noul, fresh = "crop_moved_on", 0.85, 0.85, 0.0
    elif live_paused and not live_has_board:
        cls, conf, noul, fresh = "menu_or_plate", 0.8, 0.85, 0.0
    elif live_has_board and t_hs is not None and (l_hs, l_aws) != (t_hs, t_aws):
        cls, conf, noul, fresh = "match_changed", 0.82, 0.88, 0.0
    elif gate_reason == "ticket_stale" or age_ns > STALE_AFTER_NS:
        cls, conf, noul, fresh = "clock_drift", 0.8, 0.8, 0.5
    elif age_ns > STALE_AFTER_NS * 0.5:
        cls, conf, noul, fresh = "clock_drift", 0.55, 0.55, 1.0
    else:
        cls, conf, noul, fresh = "fresh", 0.85, 0.1, 2.0

    return {
        "stale_class": cls,
        "stale_confidence": conf,
        "hold_noul": noul,
        "freshness": fresh,
        "source": "local_heuristic",
    }


class TicketStaleSentinel:
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
        self._bus = bus  # subscribe only — never emit
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
        self._flags = 0
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
        _cfg = config
        self._typesafe_timeout_s = float(
            (getattr(_cfg, "typesafe_timeout_s", DEFAULT_TIMEOUT_S) if _cfg is not None else DEFAULT_TIMEOUT_S)
            or DEFAULT_TIMEOUT_S
        )
        if not self.enabled:
            return
        out_dir = Path(getattr(config, "out_dir", "logs/ticket_stale") or "logs/ticket_stale")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            self._jsonl_handle = (out_dir / "ticket_stale.jsonl").open("a", encoding="utf-8")
        except Exception as e:
            log.debug("ticket_stale jsonl not opened: %s", e)
        if bus is not None:
            try:
                self._unsubscribe = bus.subscribe_raw(self._on_event)
            except Exception:
                try:
                    self._unsubscribe = bus.subscribe(self._on_event)
                except Exception as e:
                    log.debug("ticket_stale bus subscribe skipped: %s", e)
        self._worker = threading.Thread(
            target=self._run, name="ticket-stale-sentinel", daemon=True
        )
        self._worker.start()

    # ── hot path: enqueue only (Rule-5 class) ────────────────────────────

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

    # ── state collection (read-only accessors, never mutators) ───────────

    def _ticket_state(self) -> dict[str, Any]:
        if self._ticket_fn is not None:
            try:
                t = self._ticket_fn()
                return dict(t) if isinstance(t, dict) else {}
            except Exception:
                return {}
        try:
            from qoresence.vision.confirm_ticket import (
                get_ticket_book,
                licensed_last_confirm,
            )

            book = get_ticket_book()
            last = licensed_last_confirm(book)
            out = last.to_dict() if last is not None else {}
            out["identity_stale"] = book.identity_stale()
            return out
        except Exception:
            return {}

    def _drain_live(self) -> None:
        """Fold queued live-crop records into _latest_live (worker thread only)."""
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
                "left_team": parsed.get("left_team"),
                "right_team": parsed.get("right_team"),
                "paused": bool(parsed.get("paused")),
            }
            with self._lock:
                self._latest_live = live

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
        if live:
            return live
        try:
            from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

            last = get_scoreboard_vlm().get_last()
            return dict(last) if isinstance(last, dict) else {}
        except Exception:
            return {}

    # ── judging ──────────────────────────────────────────────────────────

    def _judge(self, state: dict[str, Any]) -> dict[str, Any]:
        answers = None
        if self._ask_fn is not None:
            answers = self._ask_fn(state)
        if answers is None:
            answers = self._try_typesafe(state)
        if answers is None:
            answers = local_stale_answers(state)
        verdict = compose_stale_verdict(
            stale_class=answers.get("stale_class"),
            stale_confidence=answers.get("stale_confidence"),
            hold_noul=answers.get("hold_noul"),
            freshness=answers.get("freshness"),
            gate_reason=state.get("gate_reason"),
        )
        verdict["source"] = answers.get("source") or "unknown"
        return verdict

    def _gate_reason(self, ticket: dict[str, Any], live: dict[str, Any]) -> str:
        """Read-only SEQGATE reason for cross-checking. Never a second gate."""
        try:
            from qoresence.sync.digit_integrity import digit_void_reason

            return digit_void_reason(
                confirm_ticket_id=str(ticket.get("ticket_id") or ""),
                score_vlm_locked=bool(ticket),
                ticket_crop_hash=str(ticket.get("crop_hash") or ""),
                live_crop_hash=str(live.get("crop_hash") or ""),
                ticket_clock_ns=int(ticket.get("clock_ns") or 0),
                live_clock_ns=int(live.get("clock_ns") or 0),
            )
        except Exception:
            return ""

    def _try_typesafe(self, state: dict[str, Any]) -> dict[str, Any] | None:
        questions = ticket_stale_questions()
        if not questions:
            return None
        payload = {
            "policy": (
                "Observation only. Never mint, restate, or license score "
                "digits. Code owns tickets, clocks, and the blank path."
            ),
            "ticket": state.get("ticket") or {},
            "live": state.get("live") or {},
            "gate_reason": state.get("gate_reason"),
            "identity_stale": bool(state.get("identity_stale")),
        }
        response = system_one(
            state=payload,
            questions=questions,
            timeout_s=self._typesafe_timeout_s,
            warn_label="ticket_stale",
            warned_flag=self._warned_typesafe,
            logger=log,
        )
        if response is None:
            return None
        choices = getattr(response, "choices", {}) or {}
        nouls = getattr(response, "nouls", {}) or {}
        scores = getattr(response, "scores", {}) or {}
        sc = choices.get("stale_class")
        hn = nouls.get("hold_now")
        fr = scores.get("freshness")
        return {
            "stale_class": getattr(sc, "choice", None) if sc is not None else None,
            "stale_confidence": (
                float(getattr(sc, "confidence", 0) or 0) if sc is not None else None
            ),
            "hold_noul": float(hn.noul) if hn is not None else None,
            "freshness": float(fr.score) if fr is not None else None,
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
                    "identity_stale": bool(ticket.get("identity_stale")),
                    "gate_reason": self._gate_reason(ticket, live),
                }
                verdict = self._judge(state)
                verdict["tick"] = self._ticks
                verdict["ts"] = time.time()
                with self._lock:
                    self._last = verdict
                    self._last_ns = time.monotonic_ns()
                    self._ticks += 1
                    self._judged += 1
                    if verdict.get("action") == "flag_stale":
                        self._flags += 1
                self._write_jsonl(verdict)
            except Exception as e:
                log.debug("ticket_stale tick failed: %s", e)

    def _write_jsonl(self, row: dict[str, Any]) -> None:
        handle = self._jsonl_handle
        if handle is None:
            return
        try:
            handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
            handle.flush()
        except Exception:
            pass

    def last(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            last = dict(self._last)
            ticks, judged, flags, dropped = (
                self._ticks,
                self._judged,
                self._flags,
                self._dropped,
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
            "flags": flags,
            "dropped": dropped,
            "last_age_s": age,
            "stale_class": last.get("stale_class"),
            "action": last.get("action"),
            "gate_reason": last.get("gate_reason"),
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


_singleton: TicketStaleSentinel | None = None
_singleton_lock = threading.Lock()


def get_ticket_stale_sentinel() -> TicketStaleSentinel | None:
    with _singleton_lock:
        return _singleton


def make_ticket_stale_from_config(
    config: Any,
    *,
    bus: Any = None,
    jev_enabled: bool = False,
    ask_fn: Any = None,
) -> TicketStaleSentinel | None:
    enabled = (
        bool(getattr(config, "enabled", False)) or jev_enabled or _env_enabled()
    )
    if not enabled:
        return None
    sen = TicketStaleSentinel(config, bus=bus, ask_fn=ask_fn)
    if not sen.enabled:
        return None
    global _singleton
    with _singleton_lock:
        _singleton = sen
    return sen
