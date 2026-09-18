"""TypeSafe Noul observatory — opt-in observation plane for gamers.

Local-first: HDMI + DualSense stay on one clock. Noul (yes-probability)
judgments sit *beside* tickets — they never license score digits, never
emit bus events, never acquire a lobe lock.

Enable with ``--noul`` or ``QORESENCE_NOUL=1``. Default OFF. ``--play``
does not turn this on.

HARD RULES (same class as AGENTS.md OTel Rules 5–6):

1. ``_on_event`` only enqueues (bounded, drop-oldest).
2. Worker may call TypeSafe (or a local heuristic) and write a small JSONL.
3. Never paint scores. Never claim clutch/highlight/eligibility.
4. Missing SDK / key / network → fail closed (no noul, no digits).

Product use: honest observatory questions a gamer can see on /health —
"does this parse look like a live scorebug?", "is this pause or preplay?",
"is pad+picture dense enough to *consider* a local clip?" Code still
owns tickets, clocks, and Foundry export.
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

from qoresence.observability.typesafe_ask import (
    DEFAULT_ASK_INTERVAL_S,
    DEFAULT_TIMEOUT_S,
    AskCadence,
    system_one,
)

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"

# Closed HUD kinds — Choice options. Include no_match.
HUD_KINDS = (
    "live_hud",
    "preplay",
    "select_plate",
    "menu",
    "loading",
    "no_board",
)

_EVENT_TYPES = frozenset(
    {
        "visual",
        "scoreboard",
        "router_decision",
        "presence_report",
        "controller",
        "coupling",
    }
)


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_NOUL", "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }


def noul_questions() -> dict[str, Any]:
    """Typed questions for System One. IDs are for code; meaning is in instructions."""
    try:
        from typesafe_sdk import Choice, Noul, Score
    except Exception:
        return {}

    return {
        "grounded_scorebug": Noul(
            instructions={
                "question": (
                    "Does `parsed` describe a live in-game scorebug for this crop "
                    "(team wordmarks or down+distance+scores on a real HUD)?"
                ),
                "true": "Live scorebug or preplay stick HUD with match identity.",
                "false": "Pause plate, menu, empty crop, or scores without teams/clock.",
                "never": "Not a digit check — code owns exact score equality.",
            },
        ),
        "true_pause": Noul(
            instructions={
                "question": (
                    "Is `parsed.paused` a true pause/SELECT menu, not preplay/Subs "
                    "gameplay with a live scorebug?"
                ),
                "true": "SELECT/pause overlay without live scorebug wordmarks.",
                "false": "Preplay, Subs, audible, or live HUD (paused flag is a false positive).",
            },
        ),
        "clip_presence": Noul(
            instructions={
                "question": (
                    "Is pad+picture co-occurrence dense enough to *consider* a "
                    "local HDMI clip?"
                ),
                "true": "High coupling with red-zone or late-close situation.",
                "false": "Idle, menu, or sparse input.",
                "never": "Not a highlight or clutch claim — observation only.",
            },
        ),
        "hud_kind": Choice(
            instructions={
                "question": "Which HUD scene is `parsed` most like?",
                "focus": "Classify the scene; code still owns digit licensing.",
                "never": "no_board when nothing usable is in the crop.",
            },
            criteria={
                "live_hud": {"what": "In-game scorebug during a snap or play."},
                "preplay": {"what": "Play-call / Subs / audible stick HUD with wordmarks."},
                "select_plate": {"what": "Pause SELECT plate that invents a score pair."},
                "menu": {"what": "Main menu, lobby, or results."},
                "loading": {"what": "Loading, cutscene, or replay."},
                "no_board": {"what": "No usable board in the crop."},
            },
        ),
        "board_honesty": Score(
            instructions={
                "question": "How honest is `parsed` as a live scorebug observation?",
                "focus": "Last-good freeze and invented pause-plate pairs are dishonest.",
                "never": "Not a quality rating of the capture pipeline.",
            },
            criteria=[
                "Invented or pause/SELECT plate; industry would keep last-good digits.",
                "Ambiguous crop; abstain is the honest act.",
                "Grounded live HUD or preplay with match identity.",
            ],
        ),
        "presence_density": Score(
            instructions={
                "question": "How dense is pad+picture co-occurrence?",
                "never": "Not clutch, highlight, or skill — join observation only.",
            },
            criteria=[
                "Idle or menu; sparse input.",
                "Some coupling without a situation peak.",
                "Dense join (red zone or late-close with pad energy).",
            ],
        ),
        "last_good_temptation": Noul(
            instructions={
                "question": (
                    "Would a last-good OCR overlay keep painting digits on this "
                    "crop when Qoresence law says blank/Ident?"
                ),
                "true": "Scores vanished or ungrounded; freeze-last-good would lie.",
                "false": "Live grounded HUD; painting licensed digits would not be a freeze lie.",
            },
        ),
    }


def compose_observatory(
    *,
    parsed: dict[str, Any] | None,
    coupling: float | None = None,
    red_zone: bool = False,
    late_close: bool = False,
    grounded_noul: float | None = None,
    true_pause_noul: float | None = None,
    clip_noul: float | None = None,
    hud_kind: str | None = None,
    hud_confidence: float | None = None,
    board_honesty: float | None = None,
    presence_density: float | None = None,
    last_good_temptation: float | None = None,
) -> dict[str, Any]:
    """Code-owned composition. Fail closed when Noul is missing or ~0.5.

    Does not license digits. ``may_consider_clip`` is presence, not export.
    """
    parsed = parsed if isinstance(parsed, dict) else {}
    has_scores = parsed.get("home_score") is not None and parsed.get(
        "away_score"
    ) is not None
    # Noul ~0.5 is coin-flip — treat as unknown, not medium intensity.
    grounded = grounded_noul is not None and grounded_noul >= 0.7
    ungrounded = grounded_noul is not None and grounded_noul <= 0.3
    pause_yes = true_pause_noul is not None and true_pause_noul >= 0.7
    kind = hud_kind if hud_kind in HUD_KINDS else None
    kind_ok = hud_confidence is None or hud_confidence >= 0.5

    board_speech = "unlocked"
    if ungrounded or kind in {"select_plate", "menu", "loading", "no_board"}:
        board_speech = "vlm_ungrounded"
    elif pause_yes and kind != "preplay":
        board_speech = "menu"
    elif grounded and kind in {"live_hud", "preplay"} and kind_ok:
        board_speech = "confirm_ticket"  # *speech only* — tickets still required
    elif not has_scores:
        board_speech = "vlm_none"

    c = float(coupling or 0.0)
    clip_ok = clip_noul is not None and clip_noul >= 0.7 and c >= 0.35
    may_consider_clip = bool(clip_ok and (red_zone or late_close))

    lattice = compose_honesty_lattice(
        board_honesty=board_honesty,
        presence_density=presence_density,
        last_good_temptation=last_good_temptation,
        grounded_noul=grounded_noul,
        hud_kind=kind if kind_ok else None,
        coupling=c,
        red_zone=red_zone,
        late_close=late_close,
    )

    return {
        "plane": PLANE,
        "grounded_noul": grounded_noul,
        "true_pause_noul": true_pause_noul,
        "clip_noul": clip_noul,
        "hud_kind": kind if kind_ok else None,
        "hud_confidence": hud_confidence,
        "board_speech": board_speech,
        "may_consider_clip": may_consider_clip,
        "licenses_digits": False,
        "has_scores": has_scores,
        **lattice,
    }


# Operator-visible composite. Weights live in code; TypeSafe supplies dimensions.
# Inverse of ScoreboardOCR "Ignore Empty → keep last-good".
HONESTY_WEIGHTS = {
    "board_honesty": 0.55,
    "presence_density": 0.25,
    "abstain_credit": 0.20,
}

PRESENCE_TOKENS = (
    "idle",
    "join",
    "dense",
)


def compose_honesty_lattice(
    *,
    board_honesty: float | None = None,
    presence_density: float | None = None,
    last_good_temptation: float | None = None,
    grounded_noul: float | None = None,
    hud_kind: str | None = None,
    coupling: float = 0.0,
    red_zone: bool = False,
    late_close: bool = False,
) -> dict[str, Any]:
    """Code-owned composite. Never a highlight rank. Never licenses digits.

    Scores are 0..2 (TypeSafe Score levels) or None. Missing dimensions
    fail-close that axis to 0 rather than inventing honesty.
    """
    honesty = float(board_honesty) if board_honesty is not None else 0.0
    dens = float(presence_density) if presence_density is not None else 0.0
    # Temptation high → last-good would lie → abstain is the *honest* credit.
    tempt = last_good_temptation
    if tempt is None:
        abstain_credit = 0.0
        ident_now = False
    else:
        ident_now = tempt >= 0.7
        abstain_credit = 2.0 if ident_now else (1.0 if tempt >= 0.4 else 0.0)

    w = HONESTY_WEIGHTS
    composite = (
        w["board_honesty"] * honesty
        + w["presence_density"] * dens
        + w["abstain_credit"] * abstain_credit
    )
    # 0..2 weighted sum → band
    if ident_now or (grounded_noul is not None and grounded_noul <= 0.3):
        band = "ident"
    elif composite >= 1.4:
        band = "ok"
    elif composite >= 0.7:
        band = "amber"
    else:
        band = "void"

    if dens >= 1.5 and coupling >= 0.5 and (red_zone or late_close):
        token = "dense"
    elif dens >= 0.7 or coupling >= 0.35:
        token = "join"
    else:
        token = "idle"

    return {
        "board_honesty": board_honesty,
        "presence_density": presence_density,
        "last_good_temptation": last_good_temptation,
        "honesty_composite": round(composite, 3),
        "honesty_band": band,
        "presence_token": token,
        "ident_now": ident_now,
        "weights": dict(w),
    }


def local_heuristic_nouls(state: dict[str, Any]) -> dict[str, Any]:
    """Offline stand-in when TypeSafe SDK/key is absent. Deterministic tests.

    Mirrors board_why rules in probability form — not a second lock path.
    """
    parsed = state.get("parsed") if isinstance(state.get("parsed"), dict) else {}
    left = str(parsed.get("left_team") or "").strip()
    right = str(parsed.get("right_team") or "").strip()
    has_teams = bool(left and right)
    has_scores = parsed.get("home_score") is not None and parsed.get(
        "away_score"
    ) is not None
    paused = bool(parsed.get("paused"))
    vc = parsed.get("visible_control") if isinstance(parsed.get("visible_control"), dict) else {}
    prompt = str(vc.get("prompt") or "").strip().lower()
    preplay = prompt in {
        "preplay",
        "subs",
        "snap",
        "flip",
        "flip play",
        "audible",
        "select play",
    } or "preplay" in prompt

    if has_teams and has_scores and (not paused or preplay):
        grounded, kind = 0.88, "preplay" if preplay else "live_hud"
    elif paused and not has_teams:
        grounded, kind = 0.12, "select_plate"
    elif not has_scores:
        grounded, kind = 0.15, "no_board"
    else:
        grounded, kind = 0.45, "no_board"

    true_pause = 0.85 if (paused and not preplay and not has_teams) else 0.12
    coup = float(state.get("coupling") or 0.0)
    red = bool(state.get("red_zone"))
    late = bool(state.get("late_close"))
    clip = 0.8 if coup >= 0.5 and (red or late) else 0.2
    if grounded >= 0.7:
        honesty, dens, tempt = 2.0, (2.0 if clip >= 0.7 else 1.0), 0.1
    elif grounded <= 0.3:
        honesty, dens, tempt = 0.0, 0.0, 0.88
    else:
        honesty, dens, tempt = 1.0, 0.5, 0.45

    return {
        "grounded_noul": grounded,
        "true_pause_noul": true_pause,
        "clip_noul": clip,
        "hud_kind": kind,
        "hud_confidence": 0.8 if grounded >= 0.7 or grounded <= 0.3 else 0.4,
        "board_honesty": honesty,
        "presence_density": dens,
        "last_good_temptation": tempt,
        "source": "local_heuristic",
    }


class NoulObservatory:
    """Enqueue-only bus subscriber; worker judges off the capture path."""

    def __init__(
        self,
        config: Any,
        bus: Any = None,
        session_identity: Any = None,
        ask_fn: Any = None,
    ) -> None:
        self.config = config
        self._dropped = 0
        self._judged = 0
        self._last_compose: dict[str, Any] = {}
        self._last_compose_ns = 0
        self._lock = threading.Lock()
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(
            maxsize=int(getattr(config, "queue_size", 256))
        )
        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None
        self._unsubscribe: Any = None
        self._ask_fn = ask_fn
        self._jsonl: Path | None = None
        self._jsonl_handle: Any = None
        ask_interval = float(
            getattr(config, "ask_interval_s", DEFAULT_ASK_INTERVAL_S)
            or DEFAULT_ASK_INTERVAL_S
        )
        self._typesafe_timeout_s = float(
            getattr(config, "typesafe_timeout_s", DEFAULT_TIMEOUT_S) or DEFAULT_TIMEOUT_S
        )
        self._ask_cadence = AskCadence(
            ask_interval_s=ask_interval, warn_label="noul"
        )
        self.enabled = bool(getattr(config, "enabled", False)) or _env_enabled()
        if not self.enabled:
            return

        out_dir = Path(getattr(config, "out_dir", "logs/noul") or "logs/noul")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            self._jsonl = out_dir / "noul.jsonl"
            self._jsonl_handle = self._jsonl.open("a", encoding="utf-8")
        except Exception as e:
            log.debug("noul jsonl not opened: %s", e)

        if bus is not None:
            try:
                self._unsubscribe = bus.subscribe_raw(self._on_event)
            except Exception:
                try:
                    self._unsubscribe = bus.subscribe(self._on_event)
                except Exception as e:
                    log.debug("noul bus subscribe skipped: %s", e)

        self._worker = threading.Thread(
            target=self._run, name="noul-observatory", daemon=True
        )
        self._worker.start()

    def _on_event(self, ev: Any) -> None:
        """Hot path: enqueue only."""
        if not self.enabled:
            return
        try:
            et = getattr(ev, "type", None)
            et_val = et.value if hasattr(et, "value") else str(et or "")
            if et_val not in _EVENT_TYPES and not str(et_val).endswith("visual"):
                payload = getattr(ev, "payload", None)
                if not isinstance(payload, dict):
                    return
                if "parsed" not in payload and "coupling" not in payload:
                    return
            rec = self._slim(ev)
            if rec is None:
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

    def _slim(self, ev: Any) -> dict[str, Any] | None:
        payload = getattr(ev, "payload", None)
        if not isinstance(payload, dict):
            payload = {}
        parsed = payload.get("parsed") or payload.get("vlm") or payload.get("last")
        if parsed is not None and not isinstance(parsed, dict):
            parsed = None
        rec = {
            "clock_ns": int(getattr(ev, "clock_ns", 0) or payload.get("clock_ns") or 0),
            "source_lobe": str(getattr(ev, "source_lobe", "") or ""),
            "event_type": str(
                getattr(getattr(ev, "type", None), "value", None)
                or getattr(ev, "type", "")
                or ""
            ),
            "parsed": parsed,
            "coupling": payload.get("coupling"),
            "red_zone": bool(payload.get("red_zone")),
            "late_close": bool(payload.get("late_close")),
        }
        if rec["parsed"] is None and rec["coupling"] is None:
            return None
        return rec

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                rec = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                self._judge(rec)
            except Exception as e:
                log.debug("noul judge skipped: %s", e)

    def _judge(self, rec: dict[str, Any]) -> None:
        parsed = rec.get("parsed")
        if not isinstance(parsed, dict) or not parsed:
            # No crop state — semantic questions have nothing to judge.
            answers = local_heuristic_nouls(rec)
            answers["source"] = "preflight"
        else:
            answers = None
            if self._ask_fn is not None:
                answers = self._ask_fn(rec)
            if answers is None:
                answers = self._ask_cadence.ask_or_reuse(
                    lambda: self._try_typesafe(rec)
                )
            if answers is None:
                answers = local_heuristic_nouls(rec)
        composed = compose_observatory(
            parsed=rec.get("parsed") if isinstance(rec.get("parsed"), dict) else {},
            coupling=rec.get("coupling") if rec.get("coupling") is not None else None,
            red_zone=bool(rec.get("red_zone")),
            late_close=bool(rec.get("late_close")),
            grounded_noul=answers.get("grounded_noul"),
            true_pause_noul=answers.get("true_pause_noul"),
            clip_noul=answers.get("clip_noul"),
            hud_kind=answers.get("hud_kind"),
            hud_confidence=answers.get("hud_confidence"),
            board_honesty=answers.get("board_honesty"),
            presence_density=answers.get("presence_density"),
            last_good_temptation=answers.get("last_good_temptation"),
        )
        composed["source"] = answers.get("source") or "unknown"
        composed["clock_ns"] = rec.get("clock_ns")
        with self._lock:
            self._last_compose = composed
            self._last_compose_ns = time.monotonic_ns()
            self._judged += 1
        self._write_jsonl(composed)

    def _try_typesafe(self, rec: dict[str, Any]) -> dict[str, Any] | None:
        questions = noul_questions()
        if not questions:
            return None
        state = {
            "parsed": rec.get("parsed") or {},
            "coupling": rec.get("coupling"),
            "red_zone": rec.get("red_zone"),
            "late_close": rec.get("late_close"),
            "policy": "observation only; never license score digits",
        }
        response = system_one(
            state=state,
            questions=questions,
            timeout_s=self._typesafe_timeout_s,
            warn_label="noul",
            warned_flag=self._ask_cadence.mark_warned(),
            logger=log,
        )
        if response is None:
            return None
        nouls = getattr(response, "nouls", {}) or {}
        choices = getattr(response, "choices", {}) or {}
        scores = getattr(response, "scores", {}) or {}
        g = nouls.get("grounded_scorebug")
        p = nouls.get("true_pause")
        c = nouls.get("clip_presence")
        lg = nouls.get("last_good_temptation")
        h = choices.get("hud_kind")
        bh = scores.get("board_honesty")
        pd = scores.get("presence_density")
        return {
            "grounded_noul": float(g.noul) if g is not None else None,
            "true_pause_noul": float(p.noul) if p is not None else None,
            "clip_noul": float(c.noul) if c is not None else None,
            "hud_kind": getattr(h, "choice", None) if h is not None else None,
            "hud_confidence": float(getattr(h, "confidence", 0) or 0)
            if h is not None
            else None,
            "board_honesty": float(bh.score) if bh is not None else None,
            "presence_density": float(pd.score) if pd is not None else None,
            "last_good_temptation": float(lg.noul) if lg is not None else None,
            "source": "typesafe",
        }

    def _write_jsonl(self, row: dict[str, Any]) -> None:
        handle = self._jsonl_handle
        if handle is None:
            return
        try:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            handle.flush()
        except Exception:
            pass

    def last(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last_compose)

    @staticmethod
    def _gamer_line(last: dict[str, Any]) -> dict[str, Any]:
        try:
            from qoresence.observability.honesty_speech import gamer_honesty_speech

            return gamer_honesty_speech(
                honesty_band=last.get("honesty_band"),
                presence_token=last.get("presence_token"),
                ident_now=bool(last.get("ident_now")),
                board_speech=last.get("board_speech"),
                enabled=True,
            )
        except Exception:
            return {"line": "", "presence": "", "ident": False, "licenses_digits": False}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            last = dict(self._last_compose)
            judged = self._judged
            last_ns = self._last_compose_ns
        age = None
        if last_ns:
            age = round((time.monotonic_ns() - last_ns) / 1e9, 3)
        return {
            "enabled": bool(self.enabled),
            "judged": judged,
            "dropped": self._dropped,
            "last_age_s": age,
            "board_speech": last.get("board_speech"),
            "hud_kind": last.get("hud_kind"),
            "may_consider_clip": last.get("may_consider_clip"),
            "licenses_digits": False,
            "source": last.get("source"),
            "honesty_band": last.get("honesty_band"),
            "honesty_composite": last.get("honesty_composite"),
            "presence_token": last.get("presence_token"),
            "ident_now": bool(last.get("ident_now")),
            "board_honesty": last.get("board_honesty"),
            "presence_density": last.get("presence_density"),
            "last_good_temptation": last.get("last_good_temptation"),
            "gamer": NoulObservatory._gamer_line(last),
            **self._ask_cadence.stats(),
        }

    def stop(self) -> None:
        self._stop_evt.set()
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            except Exception:
                pass
            self._unsubscribe = None
        if self._jsonl_handle is not None:
            try:
                self._jsonl_handle.close()
            except Exception:
                pass
            self._jsonl_handle = None


_singleton: NoulObservatory | None = None
_singleton_lock = threading.Lock()


def get_noul_observatory() -> NoulObservatory | None:
    with _singleton_lock:
        return _singleton


def _set_noul(obs: NoulObservatory | None) -> NoulObservatory | None:
    global _singleton
    with _singleton_lock:
        if obs is not None:
            _singleton = obs
        return _singleton


def make_noul_from_config(
    config: Any, bus: Any = None, session_identity: Any = None
) -> NoulObservatory | None:
    enabled = bool(getattr(config, "enabled", False)) or _env_enabled()
    if not enabled:
        return None
    obs = NoulObservatory(config, bus=bus, session_identity=session_identity)
    if not obs.enabled:
        return None
    _set_noul(obs)
    return obs
