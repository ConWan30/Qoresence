"""TicketGlass v0 — Jev judgment pack for live opt-in glass.

Speculative fan-out (one ``system_one`` call) + confidence-gated routing.
Code owns consequences. Glyphs only: lock / tension / cut. Foundry cut is
advisory — v0 never exports, arms, or cuts.

Same shape as ticket_stale / SyncCoroner (AGENTS.md Rules 5–6 class):

1. ``_on_event`` only enqueues (bounded, drop-oldest). Never blocks, never
   emits, never acquires a lobe lock.
2. A daemon worker on a situation-tick cadence (200–300 ms) judges compact
   text state via TypeSafe, falling back to a deterministic local heuristic
   (fail-closed **dark**) when the SDK/key is absent.
3. ``licenses_digits`` is False forever. ``board_paint_block`` is VETO-only:
   true forces dark board-paint; false never unlocks ConfirmTicket paint.
4. Reuses ``board.ticket_stale`` facts from the live ticket_stale pack —
   does not re-ask ``stale_class``. Does not replace scorebug VLM.
5. No Truth-plane / QorTroller wrap in state. Jev is text-only.

Opt-in: ``--ticket-glass`` / ``QORESENCE_TICKET_GLASS=1``, or under the
Jev umbrella ``--jev`` / ``QORESENCE_JEV=1``. ``--play`` does not enable.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from qoresence.observability.ticket_glass_questions import (
    CLIP_NOW,
    CONF_ACT,
    CONF_CUT,
    CONF_SOFT,
    CUT_STATES,
    GLASS_ROUTES,
    LOCK_STATES,
    MOMENT_CLASSES,
    PAINT_BLOCK_ACT,
    PAINT_BLOCK_NOT,
    PAINT_BLOCK_STATES,
    TITLE_IN_GAME_ACT,
    TITLE_IN_GAME_NOT,
    TITLE_PLANES,
    TITLE_PROFILES,
    ticket_glass_questions,
)

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"
MODEL = "jev-latest"

# Situation ticks stay fast for /health freshness; TypeSafe asks are slower.
_ASK_INTERVAL_S = 2.0
_TYPESAFE_REUSE_S = 15.0
_TYPESAFE_TIMEOUT_S = 10.0

_PIXEL_KEYS = frozenset(
    {
        "jpeg",
        "jpg",
        "png",
        "frame",
        "image",
        "base64",
        "pixels",
        "hdmi",
        "crop_jpeg",
        "frame_jpeg",
        "thumbnail",
    }
)
_TRUTH_KEYS = frozenset(
    {"truth", "qortroller", "humanity", "eligibility", "anti_cheat", "truth_plane"}
)

_LAST_N = 8

_TENSION_OPACITY = (0.0, 0.12, 0.35, 0.65)


def _truthy(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in {"1", "true", "on", "yes"}


def _env_enabled() -> bool:
    return _truthy("QORESENCE_TICKET_GLASS") or _truthy("QORESENCE_JEV")


def _key_present() -> bool:
    if os.environ.get("TYPESAFE_API_KEY", "").strip():
        return True
    try:
        p = Path(".secrets/typesafe.key")
        return p.is_file() and bool(p.stat().st_size)
    except Exception:
        return False


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _norm_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _norm_float(v: Any, default: float | None = None) -> float | None:
    if v in (None, ""):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _band(conf: float) -> str:
    if conf < CONF_SOFT:
        return "observe"
    if conf < CONF_ACT:
        return "soft"
    return "act"


def _clamp_tension(score: Any) -> int:
    try:
        n = int(round(float(score)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(3, n))


def _sanitize(obj: Any, depth: int = 0) -> Any:
    """Drop pixels and Truth-plane wrap. Text / numbers / enums only."""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            key = str(k)
            low = key.lower()
            if low in _PIXEL_KEYS or low in _TRUTH_KEYS or "base64" in low:
                continue
            if "jpeg" in low or "png" in low:
                continue
            out[key] = _sanitize(v, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [_sanitize(x, depth + 1) for x in obj[:_LAST_N]]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def compose_glass_verdict(
    *,
    title_in_game: float | None = None,
    board_paint_block: float | None = None,
    moment_class: str | None = None,
    moment_confidence: float | None = None,
    clip_now: str | None = None,
    clip_confidence: float | None = None,
    lens_tension: float | None = None,
    tension_confidence: float | None = None,
    glass_route: str | None = None,
    route_confidence: float | None = None,
    score_vlm_locked: bool = False,
    ticket_stale_action: str | None = None,
    ticket_stale_class: str | None = None,
) -> dict[str, Any]:
    """Code-owned policy. Confidence bands: >=0.7 act / 0.4-0.7 soft / <0.4 observe.

    ``board_paint_block`` is VETO-only. A low noul is *not* a ConfirmTicket
    unlock. ``cut_foundry`` needs conf>=0.85 AND title_in_game>=0.7 AND an
    explicit no-block (noul<=0.3). Ambiguous → dark. Glyphs fail-closed.
    ``licenses_digits`` is False on every output forever.

    Licensed hold: when ``score_vlm_locked`` and stale action is only
    ``watch``, ``crop_moved_on`` alone does not force lock=blocked (crop
    hash churn must not blank scorebug digits). ``flag_stale``,
    ``match_changed``, and ``menu_or_plate`` remain fail-closed.
    """
    title_noul = _norm_float(title_in_game)
    block_noul = _norm_float(board_paint_block)
    m_conf = float(moment_confidence or 0.0)
    c_conf = float(clip_confidence or 0.0)
    t_conf = float(tension_confidence or 0.0)
    r_conf = float(route_confidence or 0.0)

    title_yes = title_noul is not None and title_noul >= TITLE_IN_GAME_ACT
    title_no = title_noul is not None and title_noul <= TITLE_IN_GAME_NOT
    block_yes = block_noul is not None and block_noul >= PAINT_BLOCK_ACT
    block_clear = block_noul is not None and block_noul <= PAINT_BLOCK_NOT

    # Hard identity/menu changes always fail-closed. Soft crop hash churn
    # (crop_moved_on + action=watch) must NOT force lock=blocked while a
    # ConfirmTicket license is present — otherwise scorebug digits flicker
    # every tick as the crop hash drifts. Explicit flag_stale still blocks.
    action_flag = ticket_stale_action == "flag_stale"
    hard_stale = ticket_stale_class in {"match_changed", "menu_or_plate"}
    crop_moved = ticket_stale_class == "crop_moved_on"
    licensed_crop_watch = (
        bool(score_vlm_locked)
        and crop_moved
        and not action_flag
        and (ticket_stale_action in (None, "", "watch"))
    )
    stale_flag = bool(
        action_flag
        or hard_stale
        or (crop_moved and not licensed_crop_watch)
    )

    # lock — observational of ticket-clock + veto. Never a paint grant.
    # Sticky open-while-licensed: while ConfirmTicket is licensed, stay open
    # unless a hard veto (block_yes) or stale_flag fires. Mid-band paint is
    # observational (paint_block=watch) and must not blank scorebug digits.
    if block_yes or stale_flag:
        lock = "blocked"
    elif score_vlm_locked and not action_flag:
        lock = "open"
    else:
        lock = "unknown"
    if lock not in LOCK_STATES:
        lock = "unknown"

    if block_yes:
        paint_block = "block"
    elif block_clear:
        paint_block = "clear"
    else:
        paint_block = "watch"
    if paint_block not in PAINT_BLOCK_STATES:
        paint_block = "watch"

    mc = moment_class if moment_class in MOMENT_CLASSES else "unknown"
    if m_conf < CONF_SOFT:
        mc = "unknown"

    # tension glyph: observe → 0; soft/act may show 0–3. Opacity only on act.
    raw_tension = _clamp_tension(lens_tension) if t_conf >= CONF_SOFT else 0
    tension = raw_tension
    lens_opacity = _TENSION_OPACITY[tension] if t_conf >= CONF_ACT else 0.0

    clip = clip_now if clip_now in CLIP_NOW else "hold"
    cut_ok = (
        clip == "cut_foundry"
        and c_conf >= CONF_CUT
        and title_yes
        and block_clear
        and not stale_flag
    )
    cut = "on" if cut_ok else "off"
    if cut not in CUT_STATES:
        cut = "off"
    clip_acted = clip if (clip == "extend_window" and c_conf >= CONF_ACT and title_yes) else (
        "cut_foundry" if cut_ok else "hold"
    )

    route = glass_route if glass_route in GLASS_ROUTES else "dark"
    # Ambiguous / not in-game / low conf → dark. Soft band is glyphs only.
    if r_conf < CONF_ACT or title_no or not title_yes:
        route_acted = "dark"
    else:
        route_acted = route

    return {
        "plane": PLANE,
        "licenses_digits": False,
        "paint_unlocked": False,
        "foundry_cut": False,
        "title_in_game": round(title_noul, 3) if title_noul is not None else None,
        "board_paint_block": round(block_noul, 3) if block_noul is not None else None,
        "paint_block": paint_block,
        "moment_class": mc,
        "moment_confidence": round(m_conf, 3),
        "clip_now": clip_acted,
        "clip_now_raw": clip,
        "clip_confidence": round(c_conf, 3),
        "lens_tension": tension,
        "tension_confidence": round(t_conf, 3),
        "lens_opacity": round(lens_opacity, 3),
        "glass_route": route_acted,
        "glass_route_raw": route,
        "route_confidence": round(r_conf, 3),
        "glyphs": {
            "lock": lock,
            "tension": tension,
            "cut": cut,
        },
        "bands": {
            "moment_class": _band(m_conf),
            "clip_now": _band(c_conf),
            "lens_tension": _band(t_conf),
            "glass_route": _band(r_conf),
        },
    }


def local_glass_answers(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in when the SDK/key is absent.

    Fail-closed **dark**: hold / tension 0 / no cut. Reuses
    ``board.ticket_stale`` facts for the paint veto; never unlocks digits.
    """
    state = state if isinstance(state, dict) else {}
    title = state.get("title") if isinstance(state.get("title"), dict) else {}
    board = state.get("board") if isinstance(state.get("board"), dict) else {}
    stale = (
        board.get("ticket_stale") if isinstance(board.get("ticket_stale"), dict) else {}
    )

    plane = str(title.get("plane") or "unknown")
    if plane == "in_game" and bool(title.get("locked")):
        title_noul = 0.75
    elif plane == "in_game":
        title_noul = 0.55
    elif plane in {"menu", "pause", "loading"}:
        title_noul = 0.12
    else:
        title_noul = 0.45

    action = str(stale.get("action") or "")
    cls = str(stale.get("stale_class") or "")
    reason = str(board.get("digit_integrity_reason") or "")
    locked = bool(board.get("score_vlm_locked"))

    if action == "flag_stale" or cls in {"match_changed", "menu_or_plate"}:
        block_noul = 0.88
    elif cls == "crop_moved_on":
        # Soft crop churn while licensed + watch: stay below PAINT_BLOCK_ACT
        # so board_paint_block noul does not thrash the veto threshold.
        if locked and action in ("", "watch"):
            block_noul = 0.55
        else:
            block_noul = 0.88
    elif reason in {
        "ticket_stale",
        "crop_mismatch",
        "seq_skew",
        "no_ticket",
        "vlm_unlocked",
    }:
        block_noul = 0.82
    elif not locked:
        block_noul = 0.78
    elif action == "watch" or cls == "clock_drift":
        block_noul = 0.55
    else:
        block_noul = 0.12

    return {
        "title_in_game": title_noul,
        "board_paint_block": block_noul,
        "moment_class": "unknown",
        "moment_confidence": 0.0,
        "clip_now": "hold",
        "clip_confidence": 0.9,
        "lens_tension": 0.0,
        "tension_confidence": 0.9,
        "glass_route": "dark",
        "route_confidence": 0.9,
        "source": "local_heuristic",
    }


class TicketGlassSentinel:
    """Enqueue-only bus subscriber + timer worker. Never on the capture path."""

    def __init__(
        self,
        config: Any = None,
        *,
        bus: Any = None,
        ask_fn: Any = None,
        state_fn: Any = None,
        ticket_fn: Any = None,
        jev_enabled: bool = False,
    ) -> None:
        self.config = config
        self._bus = bus  # subscribe only — never emit
        self._ask_fn = ask_fn
        self._state_fn = state_fn
        self._ticket_fn = ticket_fn
        self._lock = threading.Lock()
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(
            maxsize=int(getattr(config, "queue_size", 256) or 256)
        )
        self._dropped = 0
        self._ticks = 0
        self._judged = 0
        self._last: dict[str, Any] = {}
        self._last_ns = 0
        self._latest_live: dict[str, Any] = {}
        self._edges: deque[str] = deque(maxlen=_LAST_N)
        self._events: deque[str] = deque(maxlen=_LAST_N)
        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None
        self._unsubscribe: Any = None
        self._jsonl_handle: Any = None
        # 200–300 ms situation tick (design). Tests may tighten cadence_s.
        self._cadence_s = float(getattr(config, "cadence_s", 0.25) or 0.25)
        self._ask_interval_s = _env_float(
            "QORESENCE_TICKET_GLASS_ASK_S",
            float(getattr(config, "ask_interval_s", _ASK_INTERVAL_S) or _ASK_INTERVAL_S),
        )
        self._typesafe_timeout_s = _env_float(
            "QORESENCE_TICKET_GLASS_TIMEOUT_S", _TYPESAFE_TIMEOUT_S
        )
        self._last_typesafe_answers: dict[str, Any] | None = None
        self._last_typesafe_ask_mono = 0.0
        self._last_typesafe_ok_mono = 0.0
        self._typesafe_asks = 0
        self._typesafe_fails = 0
        self._warned_typesafe = False
        enabled = bool(getattr(config, "enabled", False)) if config is not None else False
        self.enabled = enabled or bool(jev_enabled) or _env_enabled()
        if not self.enabled:
            return
        out_dir = Path(
            getattr(config, "out_dir", "logs/ticket_glass") or "logs/ticket_glass"
        )
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            self._jsonl_handle = (out_dir / "ticket_glass.jsonl").open("a", encoding="utf-8")
        except Exception as e:
            log.debug("ticket_glass jsonl not opened: %s", e)
        if bus is not None:
            try:
                self._unsubscribe = bus.subscribe_raw(self._on_event)
            except Exception:
                try:
                    self._unsubscribe = bus.subscribe(self._on_event)
                except Exception as e:
                    log.debug("ticket_glass bus subscribe skipped: %s", e)
        self._worker = threading.Thread(
            target=self._run, name="ticket-glass-sentinel", daemon=True
        )
        self._worker.start()

    # ── hot path: enqueue only (Rule-5 class) ────────────────────────────

    def _on_event(self, ev: Any) -> None:
        if not self.enabled:
            return
        try:
            payload = getattr(ev, "payload", None)
            if not isinstance(payload, dict):
                payload = ev if isinstance(ev, dict) else None
            if not isinstance(payload, dict):
                return
            et = str(getattr(ev, "type", None) or payload.get("type") or "")
            parsed = payload.get("parsed") or payload.get("vlm") or payload.get("last")
            if parsed is not None and not isinstance(parsed, dict):
                parsed = None
            rec = {
                "clock_ns": int(
                    getattr(ev, "clock_ns", 0) or payload.get("clock_ns") or 0
                ),
                "frame_seq": payload.get("frame_seq") or payload.get("seq"),
                "parsed": parsed,
                "crop_hash": payload.get("crop_hash"),
                "type": et,
            }
            edge = payload.get("hid_button") or payload.get("button") or payload.get("edge")
            if edge:
                rec["edge"] = str(edge)[:32]
            event_name = payload.get("event") or payload.get("kind")
            if event_name:
                rec["event"] = str(event_name)[:32]
            if (
                rec["parsed"] is None
                and not rec["crop_hash"]
                and "edge" not in rec
                and "event" not in rec
            ):
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

    def _drain_live(self) -> None:
        """Fold queued live records into _latest_live (worker thread only)."""
        while True:
            try:
                rec = self._queue.get_nowait()
            except queue.Empty:
                return
            parsed = rec.get("parsed") if isinstance(rec.get("parsed"), dict) else {}
            live = {
                "clock_ns": rec.get("clock_ns"),
                "frame_seq": rec.get("frame_seq") or parsed.get("frame_seq"),
                "crop_hash": rec.get("crop_hash") or parsed.get("crop_hash"),
                "home_score": parsed.get("home_score"),
                "away_score": parsed.get("away_score"),
                "quarter": parsed.get("quarter"),
                "clock": parsed.get("clock") or parsed.get("game_clock"),
                "down": parsed.get("down"),
                "distance": parsed.get("distance"),
                "paused": bool(parsed.get("paused")),
                "game_state": parsed.get("game_state"),
                "profile": parsed.get("profile") or parsed.get("game_profile"),
                "title_plane": parsed.get("title_plane") or parsed.get("plane"),
                "title_locked": parsed.get("title_locked") or parsed.get("locked"),
            }
            with self._lock:
                self._latest_live = {k: v for k, v in live.items() if v is not None}
                if rec.get("edge"):
                    self._edges.append(str(rec["edge"]))
                if rec.get("event"):
                    self._events.append(str(rec["event"]))

    def _ticket_stale_facts(self) -> dict[str, Any]:
        try:
            from qoresence.observability.ticket_stale import get_ticket_stale_sentinel

            sen = get_ticket_stale_sentinel()
            if sen is None:
                return {}
            last = sen.last() or {}
            return {
                "stale_class": last.get("stale_class"),
                "action": last.get("action"),
                "gate_reason": last.get("gate_reason"),
                "freshness": last.get("freshness"),
            }
        except Exception:
            return {}

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

    def _foundry_state(self) -> dict[str, Any]:
        try:
            from qoresence.vision.clip_buffer import get_clip_buffer

            st = get_clip_buffer().stats()
            cap = float(st.get("capacity") or 0) or 1.0
            frames = float(st.get("frames") or 0)
            return {
                "ring_fill": round(min(1.0, frames / cap), 3),
                "window_s": st.get("duration_s") or 0.0,
                "clip_worthy_features": {},
            }
        except Exception:
            return {"ring_fill": 0.0, "window_s": 0.0, "clip_worthy_features": {}}

    def _hid_state(self) -> dict[str, Any]:
        hid: dict[str, Any] = {
            "source": "empty",
            "edges_last_n": [],
            "apm": 0.0,
            "stick_heat": 0.0,
            "sync_lag_ms": None,
        }
        with self._lock:
            hid["edges_last_n"] = list(self._edges)
        try:
            from qoresence.sync.hid_telemetry import snapshot as _hid_snap

            snap = _hid_snap() or {}
            stick = snap.get("stick") if isinstance(snap.get("stick"), dict) else {}
            heat = 0.0
            for v in stick.values():
                if isinstance(v, dict):
                    heat = max(heat, abs(float(v.get("dx") or 0)), abs(float(v.get("dy") or 0)))
            hid["stick_heat"] = round(heat, 3)
            hid["apm"] = float(snap.get("reports_eps") or 0.0)
            if snap.get("tremor") or stick:
                hid["source"] = "usb_play"
        except Exception:
            pass
        return hid

    def _collect_state(self) -> dict[str, Any]:
        if self._state_fn is not None:
            try:
                s = self._state_fn()
                if isinstance(s, dict):
                    return _sanitize(s)
            except Exception:
                pass
        self._drain_live()
        with self._lock:
            live = dict(self._latest_live)
            events = list(self._events)
        ticket = self._ticket_state()
        stale = self._ticket_stale_facts()
        hid = self._hid_state()
        foundry = self._foundry_state()

        plane = str(live.get("title_plane") or "unknown")
        if plane not in TITLE_PLANES:
            gs = str(live.get("game_state") or "").lower()
            if gs in {"gameplay", "playing", "in_game"}:
                plane = "in_game"
            elif gs in {"menu", "lobby", "hub"}:
                plane = "menu"
            elif gs in {"paused", "pause"}:
                plane = "pause"
            elif gs in {"loading"}:
                plane = "loading"
            else:
                plane = "unknown"
        profile_raw = str(live.get("profile") or ticket.get("model") or "unknown").lower()
        if "madden" in profile_raw:
            profile = "madden"
        elif "cfb" in profile_raw or "ncaa" in profile_raw:
            profile = "cfb"
        elif "cod" in profile_raw or "duty" in profile_raw:
            profile = "cod"
        elif profile_raw in TITLE_PROFILES:
            profile = profile_raw
        else:
            profile = "unknown" if profile_raw in {"", "unknown"} else "other"

        locked = bool(ticket) and not bool(ticket.get("identity_stale"))
        reason = stale.get("gate_reason")
        if not reason:
            reason = "no_ticket" if not ticket else "ok"

        clock_ns = int(live.get("clock_ns") or ticket.get("clock_ns") or 0)
        confirm_age = None
        t_clk = int(ticket.get("clock_ns") or 0)
        if t_clk and clock_ns:
            confirm_age = max(0, clock_ns - t_clk)

        return _sanitize(
            {
                "clock_ns": clock_ns,
                "frame_seq": live.get("frame_seq") or 0,
                "intent": {
                    "play": True,
                    "lens_opacity_request": 0.0,
                    "mobile_connected": False,
                    "x_live": False,
                },
                "title": {
                    "plane": plane,
                    "profile": profile,
                    "locked": bool(live.get("title_locked")) or plane == "in_game",
                },
                "board": {
                    "score_vlm_locked": locked,
                    "digit_integrity_reason": reason,
                    "confirm_age_ns": confirm_age,
                    "soft_away": _norm_int(live.get("away_score")),
                    "soft_home": _norm_int(live.get("home_score")),
                    "ticket_away": _norm_int(ticket.get("away_score")),
                    "ticket_home": _norm_int(ticket.get("home_score")),
                    "crop_hash_live": live.get("crop_hash"),
                    "crop_hash_ticket": ticket.get("crop_hash"),
                    "ticket_stale": {
                        "stale_class": stale.get("stale_class"),
                        "action": stale.get("action"),
                        "gate_reason": stale.get("gate_reason"),
                        "freshness": stale.get("freshness"),
                    },
                },
                "situation": {
                    "quarter": live.get("quarter") or ticket.get("quarter"),
                    "clock": live.get("clock"),
                    "down": live.get("down") or ticket.get("down"),
                    "distance": live.get("distance"),
                    "ticketed": bool(ticket),
                },
                "hid": hid,
                "outcome": {"last_events": events},
                "foundry": foundry,
            }
        )

    # ── judging ──────────────────────────────────────────────────────────

    def _answers_with_typesafe_cadence(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Ask TypeSafe on a slower cadence; reuse last good vote between asks."""
        now = time.monotonic()
        if (now - self._last_typesafe_ask_mono) >= self._ask_interval_s:
            self._last_typesafe_ask_mono = now
            self._typesafe_asks += 1
            got = self._try_typesafe(state)
            if got is not None:
                self._last_typesafe_answers = dict(got)
                self._last_typesafe_ok_mono = now
                return got
            self._typesafe_fails += 1
        if (
            self._last_typesafe_answers is not None
            and (now - self._last_typesafe_ok_mono) < _TYPESAFE_REUSE_S
        ):
            return dict(self._last_typesafe_answers)
        return None

    def _judge(self, state: dict[str, Any]) -> dict[str, Any]:
        answers = None
        if self._ask_fn is not None:
            answers = self._ask_fn(state)
        if answers is None:
            answers = self._answers_with_typesafe_cadence(state)
        if answers is None:
            answers = local_glass_answers(state)
        board = state.get("board") if isinstance(state.get("board"), dict) else {}
        stale = (
            board.get("ticket_stale") if isinstance(board.get("ticket_stale"), dict) else {}
        )
        verdict = compose_glass_verdict(
            title_in_game=answers.get("title_in_game"),
            board_paint_block=answers.get("board_paint_block"),
            moment_class=answers.get("moment_class"),
            moment_confidence=answers.get("moment_confidence"),
            clip_now=answers.get("clip_now"),
            clip_confidence=answers.get("clip_confidence"),
            lens_tension=answers.get("lens_tension"),
            tension_confidence=answers.get("tension_confidence"),
            glass_route=answers.get("glass_route"),
            route_confidence=answers.get("route_confidence"),
            score_vlm_locked=bool(board.get("score_vlm_locked")),
            ticket_stale_action=stale.get("action"),
            ticket_stale_class=stale.get("stale_class"),
        )
        verdict["source"] = answers.get("source") or "unknown"
        return verdict

    def _try_typesafe(self, state: dict[str, Any]) -> dict[str, Any] | None:
        if not os.environ.get("TYPESAFE_API_KEY", "").strip():
            try:
                raw = Path(".secrets/typesafe.key").read_text(encoding="utf-8-sig").strip()
                if not raw:
                    return None
                os.environ["TYPESAFE_API_KEY"] = raw
            except Exception:
                return None
        try:
            from typesafe_sdk import TypeSafeClient
        except Exception:
            return None
        questions = ticket_glass_questions()
        if not questions:
            return None
        payload = {
            "policy": (
                "Observation only. Never mint, restate, or license score "
                "digits. board_paint_block is VETO-only — false never unlocks "
                "ConfirmTicket paint. Code owns tickets, clocks, and Foundry. "
                "Human HOLD beats every PASS. Ambiguous → dark."
            ),
            "clock_ns": state.get("clock_ns"),
            "frame_seq": state.get("frame_seq"),
            "intent": state.get("intent") or {},
            "title": state.get("title") or {},
            "board": state.get("board") or {},
            "situation": state.get("situation") or {},
            "hid": state.get("hid") or {},
            "outcome": state.get("outcome") or {},
            "foundry": state.get("foundry") or {},
        }
        model = (
            os.environ.get("QORESENCE_TICKET_GLASS_MODEL", "").strip() or MODEL
        )
        try:
            retry_kw: dict[str, Any] = {}
            try:
                from typesafe_sdk import RetryPolicy

                retry_kw["retry"] = RetryPolicy(max_retries=0)
            except Exception:
                pass
            try:
                client_cm = TypeSafeClient(
                    model=model, timeout=self._typesafe_timeout_s, **retry_kw
                )
            except TypeError:
                try:
                    client_cm = TypeSafeClient(model=model, timeout=self._typesafe_timeout_s)
                except TypeError:
                    try:
                        client_cm = TypeSafeClient(model=model)
                    except TypeError:
                        client_cm = TypeSafeClient()
            with client_cm as client:
                try:
                    response = client.system_one(
                        state=payload,
                        questions=questions,
                        timeout=self._typesafe_timeout_s,
                    )
                except TypeError:
                    response = client.system_one(state=payload, questions=questions)
            choices = getattr(response, "choices", None) or {}
            nouls = getattr(response, "nouls", None) or {}
            scores = getattr(response, "scores", None) or {}
            if not choices and not nouls and not scores:
                answers = getattr(response, "answers", None) or {}
                for name, ans in answers.items():
                    kind = getattr(ans, "type", None) or (
                        ans.get("type") if isinstance(ans, dict) else None
                    )
                    if kind == "choice":
                        choices[name] = ans
                    elif kind == "noul":
                        nouls[name] = ans
                    elif kind == "score":
                        scores[name] = ans
            tit = nouls.get("title_in_game")
            blk = nouls.get("board_paint_block")
            mc = choices.get("moment_class")
            cn = choices.get("clip_now")
            lt = scores.get("lens_tension")
            gr = choices.get("glass_route")
            return {
                "title_in_game": float(tit.noul) if tit is not None else None,
                "board_paint_block": float(blk.noul) if blk is not None else None,
                "moment_class": getattr(mc, "choice", None) if mc is not None else None,
                "moment_confidence": (
                    float(getattr(mc, "confidence", 0) or 0) if mc is not None else None
                ),
                "clip_now": getattr(cn, "choice", None) if cn is not None else None,
                "clip_confidence": (
                    float(getattr(cn, "confidence", 0) or 0) if cn is not None else None
                ),
                "lens_tension": float(lt.score) if lt is not None else None,
                "tension_confidence": (
                    float(getattr(lt, "confidence", 0) or 0) if lt is not None else None
                ),
                "glass_route": getattr(gr, "choice", None) if gr is not None else None,
                "route_confidence": (
                    float(getattr(gr, "confidence", 0) or 0) if gr is not None else None
                ),
                "source": "typesafe",
            }
        except Exception as e:
            if not self._warned_typesafe:
                self._warned_typesafe = True
                log.warning(
                    "ticket_glass system_one failed (%s): %s",
                    type(e).__name__,
                    e,
                )
            else:
                log.debug("ticket_glass system_one failed: %s", e)
            return None

    # ── worker ───────────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_evt.wait(self._cadence_s):
            try:
                state = self._collect_state()
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
                log.debug("ticket_glass tick failed: %s", e)

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
            ticks, judged, dropped = self._ticks, self._judged, self._dropped
            last_ns = self._last_ns
        age = None
        if last_ns:
            age = round((time.monotonic_ns() - last_ns) / 1e9, 3)
        glyphs = last.get("glyphs") if isinstance(last.get("glyphs"), dict) else {}
        return {
            "enabled": bool(self.enabled),
            "key_present": _key_present(),
            "ticks": ticks,
            "judged": judged,
            "dropped": dropped,
            "last_age_s": age,
            "glyphs": {
                "lock": glyphs.get("lock"),
                "tension": glyphs.get("tension"),
                "cut": glyphs.get("cut"),
            },
            "glass_route": last.get("glass_route"),
            "moment_class": last.get("moment_class"),
            "clip_now": last.get("clip_now"),
            "title_in_game": last.get("title_in_game"),
            "board_paint_block": last.get("board_paint_block"),
            "paint_block": last.get("paint_block"),
            "source": last.get("source"),
            "typesafe_asks": self._typesafe_asks,
            "typesafe_fails": self._typesafe_fails,
            "ask_interval_s": self._ask_interval_s,
            "licenses_digits": False,
            "paint_unlocked": False,
            "foundry_cut": False,
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


_singleton: TicketGlassSentinel | None = None
_singleton_lock = threading.Lock()


def get_ticket_glass() -> TicketGlassSentinel | None:
    with _singleton_lock:
        return _singleton


def make_ticket_glass_from_config(
    config: Any,
    *,
    bus: Any = None,
    jev_enabled: bool = False,
    ask_fn: Any = None,
    state_fn: Any = None,
) -> TicketGlassSentinel | None:
    enabled = bool(getattr(config, "enabled", False)) or jev_enabled or _env_enabled()
    if not enabled:
        return None
    sen = TicketGlassSentinel(
        config,
        bus=bus,
        ask_fn=ask_fn,
        state_fn=state_fn,
        jev_enabled=jev_enabled,
    )
    if not sen.enabled:
        return None
    global _singleton
    with _singleton_lock:
        _singleton = sen
    return sen