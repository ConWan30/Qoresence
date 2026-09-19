"""Join picker — Jev selects an already-stamped hid_seq_line slot.

Second clock over pad↔picture evidence. Code still owns IVC, Bind, PLL, and
ghost-stick paint. Jev never invents a lag, never interpolates, never writes
lag_center, never licenses digits.

Same shape as mint_verifier / ticket_stale (AGENTS.md Rules 5–6):

1. Timer worker only. Never on grab / HID / bus-subscriber hot path.
2. TypeSafe or local heuristic; compose in code.
3. ``licenses_digits`` is False forever. v0 ``action`` is advisory speech;
   ghost-stick actuation is a later flag.

Opt-in: ``--join-picker`` / ``QORESENCE_JOIN_PICKER=1``, or under ``--jev``.
``--play`` does not enable.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from qoresence.observability.jev_ledger import append_judgment
from qoresence.observability.join_picker_questions import (
    ACT_KINDS,
    ACTIONS,
    CONF_ACT,
    CONF_SOFT,
    JOIN_IDS,
    MENU_HUD,
    PLAY_PHASES,
    join_picker_questions,
)
from qoresence.observability.typesafe_ask import (
    DEFAULT_TIMEOUT_S,
    system_one,
)
from qoresence.sync.ghost_stick import IDLE_STICK, IDLE_TRIGGER

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"
SLOT_OFFSETS = (("behind_2", -2), ("behind_1", -1), ("now", 0), ("ahead_1", 1))


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_JOIN_PICKER", "").strip().lower() in {
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


def _norm_float(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _idle_slot(slot: dict[str, Any]) -> bool:
    if not slot.get("present"):
        return True
    mag = float(slot.get("stick_mag") or 0.0)
    r2 = float(slot.get("r2") or 0.0)
    l2 = float(slot.get("l2") or 0.0)
    return mag < IDLE_STICK and r2 < IDLE_TRIGGER and l2 < IDLE_TRIGGER


def slot_from_sample(sample: Any) -> dict[str, Any]:
    """Facts from a stored HidSeqSample. Never interpolates."""
    if sample is None:
        return {"present": False}
    try:
        lx = float(getattr(sample, "lx", 0.0) or 0.0)
        ly = float(getattr(sample, "ly", 0.0) or 0.0)
        r2 = float(getattr(sample, "r2", 0.0) or 0.0)
        l2 = float(getattr(sample, "l2", 0.0) or 0.0)
        hub_ns = int(getattr(sample, "hub_clock_ns", 0) or 0)
        hid_ns = int(getattr(sample, "hid_clock_ns", 0) or 0)
        lag_ms = (hub_ns - hid_ns) / 1e6 if hub_ns and hid_ns else None
        mag = (lx * lx + ly * ly) ** 0.5
        buttons = tuple(getattr(sample, "buttons", ()) or ())
        return {
            "present": True,
            "seq": int(getattr(sample, "hub_seq", 0) or 0),
            "lag_ms": None if lag_ms is None else round(lag_ms, 2),
            "lx": round(lx, 3),
            "ly": round(ly, 3),
            "r2": round(r2, 3),
            "l2": round(l2, 3),
            "stick_mag": round(mag, 3),
            "buttons": list(buttons),
            "idle": mag < IDLE_STICK and r2 < IDLE_TRIGGER and l2 < IDLE_TRIGGER,
        }
    except Exception:
        return {"present": False}


def build_candidates(
    samples: dict[int, Any] | None,
    hub_seq: int,
) -> dict[str, Any]:
    """Map hid_seq_line neighbors onto stable Choice ids. No InputRing.now."""
    seq = int(hub_seq or 0)
    bag = samples if isinstance(samples, dict) else {}
    out: dict[str, Any] = {}
    for name, delta in SLOT_OFFSETS:
        sample = bag.get(seq + delta)
        out[name] = slot_from_sample(sample)
    return out


def compose_join_verdict(
    *,
    join_id: str | None = None,
    join_confidence: float | None = None,
    picture_answered: float | None = None,
    join_honesty: float | None = None,
    act_kind: str | None = None,
    candidates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Code-owned policy. Choice conf and Noul probability are the gates."""
    slots = candidates if isinstance(candidates, dict) else {}
    present = {k for k, v in slots.items() if isinstance(v, dict) and v.get("present")}
    jid = join_id if join_id in JOIN_IDS else "none"
    conf = float(join_confidence or 0.0)
    noul = picture_answered
    honesty = float(join_honesty) if join_honesty is not None else None
    kind = act_kind if act_kind in ACT_KINDS else "unknown"

    if jid != "none" and jid not in present:
        jid = "none"

    if not present or jid == "none":
        action = "dark"
        jid = "none"
    elif noul is not None and noul <= 0.3:
        action = "dark"
        jid = "none"
    elif conf < CONF_SOFT:
        action = "dark"
        jid = "none"
    elif (
        noul is not None
        and noul >= CONF_ACT
        and (conf >= CONF_ACT or (conf >= CONF_SOFT and honesty is not None and honesty >= 1.5))
    ):
        action = "stamp"
    else:
        action = "observe"
    if action not in ACTIONS:
        action = "observe"

    chosen = slots.get(jid) if jid != "none" else {}
    if not isinstance(chosen, dict):
        chosen = {}
    return {
        "plane": PLANE,
        "action": action,
        "join_id": jid,
        "join_confidence": round(conf, 3),
        "join_seq": chosen.get("seq"),
        "join_lag_ms": chosen.get("lag_ms"),
        "picture_answered": noul,
        "join_honesty": honesty,
        "act_kind": kind if jid != "none" else "unknown",
        "licenses_digits": False,
    }


def local_join_answers(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in when the SDK/key is absent."""
    candidates = state.get("candidates") if isinstance(state.get("candidates"), dict) else {}
    picture = state.get("picture") if isinstance(state.get("picture"), dict) else {}
    center = _norm_float(picture.get("lag_center_ms")) or 80.0
    hud = str(picture.get("hud_kind") or "").strip().lower()
    phase = str(picture.get("visual_phase") or "").strip().lower()
    game = str(picture.get("game_state") or "").strip().lower()
    menu = hud in MENU_HUD or game in {"menu", "lobby", "paused", "pause", "loading"}

    best_id = "none"
    best_dist = 1e9
    for name, _delta in SLOT_OFFSETS:
        slot = candidates.get(name) if isinstance(candidates.get(name), dict) else {}
        if not slot.get("present") or _idle_slot(slot):
            continue
        lag = _norm_float(slot.get("lag_ms"))
        if lag is None:
            dist = 40.0
        else:
            dist = abs(lag - center)
        if dist < best_dist:
            best_dist = dist
            best_id = name

    slot = candidates.get(best_id) if isinstance(candidates.get(best_id), dict) else {}
    idle = _idle_slot(slot) if best_id != "none" else True
    if menu or idle or best_id == "none":
        answered = 0.2
        honesty = 0.0
        act = "menu_stick" if menu else "idle"
        jid = "none"
        conf = 0.85
    else:
        live_phase = phase in PLAY_PHASES or phase in {"snap", "running"}
        answered = 0.8 if live_phase or not phase else 0.55
        honesty = 2.0 if best_dist <= 40.0 and answered >= 0.7 else 1.0
        r2 = float(slot.get("r2") or 0.0)
        mag = float(slot.get("stick_mag") or 0.0)
        if r2 >= 0.4 and phase in {"snap", ""}:
            act = "snap"
        elif mag >= 0.3 and phase in {"running", "defense_pursuit", ""}:
            act = "sprint"
        else:
            act = "unknown"
        jid = best_id
        conf = 0.85
        if answered < 0.7:
            answered = 0.55

    return {
        "join_id": jid,
        "join_confidence": conf,
        "picture_answered": answered,
        "join_honesty": honesty,
        "act_kind": act if act in ACT_KINDS else "unknown",
        "source": "local_heuristic",
    }


def _picture_state() -> dict[str, Any]:
    picture: dict[str, Any] = {}
    try:
        from qoresence.sync.ivc import get_last_coupling

        coup = get_last_coupling() or {}
        picture["lag_center_ms"] = coup.get("lag_center_ms")
        picture["pll_lock"] = coup.get("pll_lock")
        picture["last_bind_kind"] = coup.get("last_bind_kind")
        picture["last_bind_hid"] = coup.get("last_bind_hid")
        picture["last_bind_ms"] = coup.get("last_bind_ms")
        picture["frame_seq"] = coup.get("frame_seq")
        picture["game_state"] = coup.get("game_state")
    except Exception:
        pass
    try:
        from qoresence.observability.noul_observatory import get_noul_observatory

        noul = get_noul_observatory()
        if noul is not None:
            stats = noul.stats() if hasattr(noul, "stats") else {}
            picture["hud_kind"] = stats.get("hud_kind")
    except Exception:
        pass
    try:
        from qoresence.lobes.visual import get_last_visual_context

        ctx = get_last_visual_context()
        if ctx is not None:
            details = getattr(ctx, "details", None) or {}
            picture.setdefault("visual_phase", details.get("visual_phase") if isinstance(details, dict) else None)
            picture.setdefault("game_state", getattr(ctx, "game_state", None))
    except Exception:
        pass
    return picture


def _hub_seq(picture: dict[str, Any]) -> int:
    try:
        from qoresence.monitor.frame_hub import get_frame_hub

        seq = int(get_frame_hub().stats().get("seq") or 0)
        if seq:
            return seq
    except Exception:
        pass
    try:
        return int(picture.get("frame_seq") or 0)
    except (TypeError, ValueError):
        return 0


class JoinPickerSentinel:
    """Timer worker. Reads hid_seq_line; never writes PLL or ghost stick in v0."""

    def __init__(
        self,
        config: Any = None,
        *,
        ask_fn: Any = None,
        candidates_fn: Any = None,
        picture_fn: Any = None,
        hub_seq_fn: Any = None,
    ) -> None:
        self.config = config
        self._ask_fn = ask_fn
        self._candidates_fn = candidates_fn
        self._picture_fn = picture_fn
        self._hub_seq_fn = hub_seq_fn
        self._lock = threading.Lock()
        self._ticks = 0
        self._judged = 0
        self._asked = 0
        self._last: dict[str, Any] = {}
        self._last_ns = 0
        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None
        self._jsonl_handle: Any = None
        self._cadence_s = float(getattr(config, "cadence_s", 0.5) or 0.5)
        enabled = bool(getattr(config, "enabled", False)) if config is not None else False
        self.enabled = enabled or _env_enabled()
        self._warned_typesafe = [False]
        timeout = DEFAULT_TIMEOUT_S
        if config is not None:
            timeout = float(getattr(config, "typesafe_timeout_s", DEFAULT_TIMEOUT_S) or DEFAULT_TIMEOUT_S)
        self._typesafe_timeout_s = timeout
        if not self.enabled:
            return
        out_dir = Path(getattr(config, "out_dir", "logs/join_picker") or "logs/join_picker")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            self._jsonl_handle = (out_dir / "join_picker.jsonl").open("a", encoding="utf-8")
        except Exception as e:
            log.debug("join_picker jsonl not opened: %s", e)
        self._worker = threading.Thread(target=self._run, name="join-picker", daemon=True)
        self._worker.start()

    def _candidates(self, hub_seq: int) -> dict[str, Any]:
        if self._candidates_fn is not None:
            try:
                got = self._candidates_fn(hub_seq)
                if isinstance(got, dict) and "now" in got:
                    return got
                if isinstance(got, dict):
                    return build_candidates(got, hub_seq)
            except Exception:
                return {name: {"present": False} for name, _ in SLOT_OFFSETS}
        try:
            from qoresence.sync.hid_seq_line import get_window

            samples = get_window(hub_seq, behind=2, ahead=1)
            return build_candidates(samples, hub_seq)
        except Exception:
            return {name: {"present": False} for name, _ in SLOT_OFFSETS}

    def _judge(self, state: dict[str, Any]) -> dict[str, Any]:
        answers = None
        if self._ask_fn is not None:
            answers = self._ask_fn(state)
        if answers is None:
            answers = self._try_typesafe(state)
        if answers is None:
            answers = local_join_answers(state)
        verdict = compose_join_verdict(
            join_id=answers.get("join_id"),
            join_confidence=answers.get("join_confidence"),
            picture_answered=answers.get("picture_answered"),
            join_honesty=answers.get("join_honesty"),
            act_kind=answers.get("act_kind"),
            candidates=state.get("candidates"),
        )
        verdict["source"] = answers.get("source") or "unknown"
        return verdict

    def _try_typesafe(self, state: dict[str, Any]) -> dict[str, Any] | None:
        questions = join_picker_questions()
        if not questions:
            return None
        payload = {
            "policy": {
                "never_mint": True,
                "never_invent_lag": True,
                "never_interpolate": True,
            },
            "candidates": state.get("candidates") or {},
            "picture": state.get("picture") or {},
        }
        response = system_one(
            state=payload,
            questions=questions,
            timeout_s=self._typesafe_timeout_s,
            warn_label="join_picker",
            warned_flag=self._warned_typesafe,
            logger=log,
        )
        if response is None:
            return None
        self._asked += 1
        choices = getattr(response, "choices", {}) or {}
        nouls = getattr(response, "nouls", {}) or {}
        scores = getattr(response, "scores", {}) or {}
        jid = choices.get("join_id")
        act = choices.get("act_kind")
        pa = nouls.get("picture_answered")
        hon = scores.get("join_honesty")
        return {
            "join_id": getattr(jid, "choice", None) if jid is not None else None,
            "join_confidence": (
                float(getattr(jid, "confidence", 0) or 0) if jid is not None else 0.0
            ),
            "picture_answered": float(pa.noul) if pa is not None else None,
            "join_honesty": float(getattr(hon, "score", 0) or 0) if hon is not None else None,
            "act_kind": getattr(act, "choice", None) if act is not None else None,
            "source": "typesafe",
        }

    def _run(self) -> None:
        while not self._stop_evt.wait(self._cadence_s):
            try:
                picture = self._picture_fn() if self._picture_fn else _picture_state()
                if not isinstance(picture, dict):
                    picture = {}
                if self._hub_seq_fn is not None:
                    hub_seq = int(self._hub_seq_fn() or 0)
                else:
                    hub_seq = _hub_seq(picture)
                candidates = self._candidates(hub_seq)
                state = {"candidates": candidates, "picture": picture, "hub_seq": hub_seq}
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
                log.debug("join_picker tick failed: %s", e)

    def _write_jsonl(self, row: dict[str, Any]) -> None:
        append_judgment("join_picker", row)
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
            ticks, judged, asked = self._ticks, self._judged, self._asked
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
            "last_age_s": age,
            "action": last.get("action"),
            "join_id": last.get("join_id"),
            "join_seq": last.get("join_seq"),
            "join_lag_ms": last.get("join_lag_ms"),
            "picture_answered": last.get("picture_answered"),
            "join_honesty": last.get("join_honesty"),
            "act_kind": last.get("act_kind"),
            "source": last.get("source"),
            "licenses_digits": False,
        }

    def stop(self) -> None:
        self._stop_evt.set()
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=2.0)
        if self._jsonl_handle is not None:
            try:
                self._jsonl_handle.close()
            except Exception:
                pass
            self._jsonl_handle = None


_singleton: JoinPickerSentinel | None = None
_singleton_lock = threading.Lock()


def get_join_picker() -> JoinPickerSentinel | None:
    with _singleton_lock:
        return _singleton


def make_join_picker_from_config(
    config: Any,
    *,
    jev_enabled: bool = False,
    ask_fn: Any = None,
) -> JoinPickerSentinel | None:
    enabled = bool(getattr(config, "enabled", False)) or jev_enabled or _env_enabled()
    if not enabled:
        return None
    cfg = config
    if jev_enabled and not bool(getattr(config, "enabled", False)):
        try:
            from dataclasses import replace

            from qoresence.core.unified_config import JoinPickerConfig

            cfg = replace(
                config if config is not None else JoinPickerConfig(),
                enabled=True,
            )
        except Exception:
            cfg = config
    sen = JoinPickerSentinel(cfg, ask_fn=ask_fn)
    if not sen.enabled:
        return None
    global _singleton
    with _singleton_lock:
        _singleton = sen
    return sen
