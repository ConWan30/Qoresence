"""Shadow score-transition diagnostics, never a live veto or digit license.

Score deltas alone cannot establish a misread: observations may span multiple
plays or correct an earlier extraction. Legacy flag_veto actions describe what
the previous policy would have done, not an instruction to the mint path.

Opt-in via --jev / QORESENCE_JEV=1. Network and audit writes stay on the
worker, never the capture/HID/bus threads. No bus emissions or lobe locks.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from qoresence.sync.digit_integrity import implausible_transition_reason

from qoresence.observability.typesafe_ask import (
    DEFAULT_TIMEOUT_S,
    system_one,
)

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"

# Noul has no separate confidence; the probability itself is the gate.
# >= ACT flags a veto; SOFT..ACT is watch; < SOFT / missing is observe.
_NOUL_ACT = 0.7
_NOUL_SOFT = 0.4

JUMP_KINDS = (
    "legal_score",
    "ocr_echo",
    "score_drop",
    "both_sides",
    "clock_leak",
    "unknown",
)

ACTIONS = ("flag_veto", "watch", "observe")


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_JEV", "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }


def _score_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def plausibility_questions() -> dict[str, Any]:
    """One call: implausible Noul + speculative jump-kind Choice.

    Question IDs are for code; meaning lives in instructions. The Choice is
    diagnostic only — code consumes it when the Noul is high enough to care.
    """
    try:
        from typesafe_sdk import Choice, Noul
    except Exception:
        return {}
    return {
        "implausible": Noul(
            instructions={
                "question": (
                    "Given `prior` (the last licensed score pair) and "
                    "`proposed` (the pair the seeing path wants to mint), "
                    "is this score transition implausible as a real "
                    "American-football scoring play?"
                ),
                "true": (
                    "Not a legal one-team increment, a drop, both sides "
                    "moved, or a classic OCR echo (20-0 → 20-20)."
                ),
                "false": (
                    "A legal one-team football increment (safety/FG/TD/"
                    "PAT/2pt) or an unchanged pair."
                ),
                "never": (
                    "Observation only — never license or restate digits. "
                    "Code owns the refuse."
                ),
            },
        ),
        "jump_kind": Choice(
            instructions={
                "question": (
                    "Assuming the transition from `prior` to `proposed` is "
                    "a misread rather than a real score, which class best "
                    "describes it?"
                ),
                "focus": "Classify the jump. Code owns every refuse.",
                "never": "Never prescribe a score; never mint digits.",
            },
            criteria={
                "legal_score": {
                    "what": "Looks like a real one-team football increment.",
                },
                "ocr_echo": {
                    "what": (
                        "One side copied onto the other (20-0 → 20-20) or "
                        "a digit doubled."
                    ),
                },
                "score_drop": {
                    "what": "A side decreased — scores do not drop mid-game.",
                },
                "both_sides": {
                    "what": "Both sides changed in one tick; vanishingly rare.",
                },
                "clock_leak": {
                    "what": (
                        "The new digits look like a clock, down, or quarter "
                        "leaking into a score field."
                    ),
                },
                "unknown": {"what": "Not enough evidence to classify."},
            },
        ),
    }


def local_plausibility(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in when the SDK/key is absent."""
    prior = state.get("prior") if isinstance(state.get("prior"), dict) else {}
    proposed = (
        state.get("proposed") if isinstance(state.get("proposed"), dict) else {}
    )
    reason = implausible_transition_reason(
        prior.get("home_score"),
        prior.get("away_score"),
        proposed.get("home_score"),
        proposed.get("away_score"),
    )
    oh, oa = _score_int(prior.get("home_score")), _score_int(prior.get("away_score"))
    nh, na = _score_int(proposed.get("home_score")), _score_int(
        proposed.get("away_score")
    )
    kind = "unknown"
    if oh is not None and oa is not None and nh is not None and na is not None:
        dh, da = nh - oh, na - oa
        if dh == 0 and da == 0:
            kind = "legal_score"
        elif dh < 0 or da < 0:
            kind = "score_drop"
        elif dh != 0 and da != 0:
            kind = "ocr_echo" if nh == oh or na == oa or nh == na else "both_sides"
        elif reason is None:
            kind = "legal_score"
        else:
            kind = "ocr_echo"
    noul = 0.85 if reason else 0.15
    return {
        "implausible_noul": noul,
        "jump_kind": kind,
        "jump_confidence": 0.85,
        "source": "local_heuristic",
        "local_reason": reason,
    }


def compose_verdict(
    *,
    implausible_noul: float | None,
    jump_kind: str | None = None,
    jump_confidence: float | None = None,
    local_reason: str | None = None,
) -> dict[str, Any]:
    """Code-owned policy. High implausible-noul may only add a veto."""
    noul = float(implausible_noul) if implausible_noul is not None else None
    kind = jump_kind if jump_kind in JUMP_KINDS else "unknown"
    conf = float(jump_confidence) if jump_confidence is not None else None
    local = str(local_reason or "") or None

    if local == "implausible_transition" or (noul is not None and noul >= _NOUL_ACT):
        action = "flag_veto"
    elif noul is not None and noul >= _NOUL_SOFT:
        action = "watch"
    else:
        action = "observe"
    return {
        "plane": PLANE,
        "implausible_noul": None if noul is None else round(noul, 3),
        "jump_kind": kind,
        "jump_confidence": None if conf is None else round(conf, 3),
        "local_reason": local,
        "action": action,
        "licenses_digits": False,
        "mode": "shadow",
        "enforces_veto": False,
    }


class ScorePlausibility:
    """Timer-driven semantic observer. Never on the capture path."""

    def __init__(
        self,
        config: Any = None,
        *,
        bus: Any = None,
        ask_fn: Any = None,
    ) -> None:
        self.config = config
        self._bus = bus  # stats only — never emit, never subscribe
        self._ask_fn = ask_fn
        self.enabled = bool(getattr(config, "enabled", False)) or _env_enabled()
        self._warned_typesafe = [False]
        self._typesafe_timeout_s = float(
            getattr(config, "typesafe_timeout_s", DEFAULT_TIMEOUT_S)
            or DEFAULT_TIMEOUT_S
        )
        self._cadence_s = float(getattr(config, "cadence_s", 3.0) or 3.0)
        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._ticks = 0
        self._last_state_key: str | None = None
        self._flagged = 0
        self._last: dict[str, Any] = {}
        self._last_ns = 0
        self._veto_key: tuple[int, int, int, int] | None = None
        self._jsonl_handle: Any = None
        if not self.enabled:
            return
        out_dir = Path(
            getattr(config, "out_dir", "logs/score_plausibility")
            or "logs/score_plausibility"
        )
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            self._jsonl_handle = (out_dir / "score_plausibility.jsonl").open(
                "a", encoding="utf-8"
            )
        except Exception as e:
            log.debug("score_plausibility jsonl not opened: %s", e)
        self._worker = threading.Thread(
            target=self._run, name="score-plausibility", daemon=True
        )
        self._worker.start()
        log.info("ScorePlausibility started (cadence %.1fs)", self._cadence_s)

    def _collect(self) -> dict[str, Any]:
        prior: dict[str, Any] = {}
        proposed: dict[str, Any] = {}
        refuse_reason = ""
        refused = last_refused()
        if refused:
            prior = dict(refused.get("prior") or {})
            proposed = dict(refused.get("proposed") or {})
            refuse_reason = str(refused.get("reason") or "")
        else:
            try:
                from qoresence.vision.confirm_ticket import get_ticket_book

                book = get_ticket_book()
                ident = book.last_board_identity() if book is not None else None
                if ident is not None:
                    prior = {
                        "home_score": ident[0],
                        "away_score": ident[1],
                        "home_team": ident[2],
                        "away_team": ident[3],
                    }
                    proposed = {
                        "home_score": ident[0],
                        "away_score": ident[1],
                    }
            except Exception:
                pass
        return {
            "policy": (
                "Diagnosis only. Code owns tickets, clocks, and digit "
                "licensing. Never prescribe a score."
            ),
            "prior": prior,
            "proposed": proposed,
            "refuse_reason": refuse_reason,
        }

    def _judge(self, state: dict[str, Any]) -> dict[str, Any]:
        answers = None
        model_called = False
        if self._ask_fn is not None:
            answers = self._ask_fn(state)
            model_called = True
        if answers is None:
            local = local_plausibility(state)
            # Only burn a model call on a refused / implausible jump —
            # a healthy unchanged board needs no diagnosis.
            refused = str(state.get("refuse_reason") or "") == "implausible_transition"
            if local.get("local_reason") == "implausible_transition" or refused:
                answers = self._try_typesafe(state) or local
                model_called = model_called or answers is not local
            else:
                answers = local
        if answers is None:
            answers = local_plausibility(state)
        verdict = compose_verdict(
            implausible_noul=answers.get("implausible_noul"),
            jump_kind=answers.get("jump_kind"),
            jump_confidence=answers.get("jump_confidence"),
            local_reason=answers.get("local_reason")
            or implausible_transition_reason(
                (state.get("prior") or {}).get("home_score"),
                (state.get("prior") or {}).get("away_score"),
                (state.get("proposed") or {}).get("home_score"),
                (state.get("proposed") or {}).get("away_score"),
            ),
        )
        verdict["source"] = answers.get("source") or "unknown"
        verdict["model_called"] = bool(model_called)
        return verdict

    def _try_typesafe(self, state: dict[str, Any]) -> dict[str, Any] | None:
        questions = plausibility_questions()
        if not questions:
            return None
        response = system_one(
            state=state,
            questions=questions,
            timeout_s=self._typesafe_timeout_s,
            warn_label="score_plausibility",
            warned_flag=self._warned_typesafe,
            logger=log,
        )
        if response is None:
            return None
        nouls = getattr(response, "nouls", {}) or {}
        choices = getattr(response, "choices", {}) or {}
        n = nouls.get("implausible")
        c = choices.get("jump_kind")
        return {
            "implausible_noul": (
                float(n.noul) if n is not None else None
            ),
            "jump_kind": getattr(c, "choice", None) if c is not None else None,
            "jump_confidence": (
                float(getattr(c, "confidence", 0) or 0) if c is not None else None
            ),
            "source": "typesafe",
        }

    def _run(self) -> None:
        while not self._stop_evt.wait(self._cadence_s):
            try:
                state = self._collect()
                state_key = json.dumps(state, sort_keys=True)
                if state_key == self._last_state_key:
                    continue
                self._last_state_key = state_key
                verdict = self._judge(state)
                verdict["tick"] = self._ticks
                verdict["ts"] = time.time()
                prior = state.get("prior") or {}
                proposed = state.get("proposed") or {}
                key = None
                oh, oa = _score_int(prior.get("home_score")), _score_int(
                    prior.get("away_score")
                )
                nh, na = _score_int(proposed.get("home_score")), _score_int(
                    proposed.get("away_score")
                )
                if None not in (oh, oa, nh, na):
                    key = (oh, oa, nh, na)
                with self._lock:
                    self._last = verdict
                    self._last_ns = time.monotonic_ns()
                    self._ticks += 1
                    if verdict.get("action") == "flag_veto":
                        self._flagged += 1
                        self._veto_key = key
                    elif key is not None and self._veto_key == key:
                        pass
                    else:
                        # A different (or missing) pair — drop a stale veto.
                        if self._veto_key is not None and self._veto_key != key:
                            self._veto_key = None
                self._write_jsonl(verdict)
            except Exception as e:
                log.debug("score_plausibility tick failed: %s", e)

    def _write_jsonl(self, row: dict[str, Any]) -> None:
        handle = self._jsonl_handle
        if handle is None:
            return
        try:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            handle.flush()
        except Exception:
            pass

    def veto_matches(
        self,
        prior_home: Any,
        prior_away: Any,
        home: Any,
        away: Any,
    ) -> bool:
        """Compatibility hook: shadow judgments never veto live candidates."""
        return False

    def stats(self) -> dict[str, Any]:
        with self._lock:
            last = dict(self._last)
            ticks, flagged = self._ticks, self._flagged
            last_ns = self._last_ns
        age = None
        if last_ns:
            age = round((time.monotonic_ns() - last_ns) / 1e9, 3)
        return {
            "enabled": bool(self.enabled),
            "ticks": ticks,
            "flagged": flagged,
            "last_age_s": age,
            "action": last.get("action"),
            "jump_kind": last.get("jump_kind"),
            "implausible_noul": last.get("implausible_noul"),
            "source": last.get("source"),
            "licenses_digits": False,
            "mode": "shadow",
            "enforces_veto": False,
        }

    def stop(self) -> None:
        self._stop_evt.set()
        if self._jsonl_handle is not None:
            try:
                self._jsonl_handle.close()
            except Exception:
                pass
            self._jsonl_handle = None


_refuse_lock = threading.Lock()
_last_refuse: dict[str, Any] | None = None


def note_refused(
    *,
    prior_home: Any,
    prior_away: Any,
    home: Any,
    away: Any,
    reason: str,
) -> None:
    """Mint-path refuse slot — newest-wins, no bus, no lobe lock."""
    global _last_refuse
    with _refuse_lock:
        _last_refuse = {
            "prior": {"home_score": prior_home, "away_score": prior_away},
            "proposed": {"home_score": home, "away_score": away},
            "reason": str(reason or ""),
        }


def last_refused() -> dict[str, Any] | None:
    with _refuse_lock:
        return dict(_last_refuse) if _last_refuse else None


def reset_score_plausibility() -> None:
    """Tests: drop singleton, refuse slot, and stop a live worker."""
    global _singleton, _last_refuse
    with _singleton_lock:
        sp = _singleton
        _singleton = None
    if sp is not None:
        try:
            sp.stop()
        except Exception:
            pass
    with _refuse_lock:
        _last_refuse = None


_singleton: ScorePlausibility | None = None
_singleton_lock = threading.Lock()


def get_score_plausibility() -> ScorePlausibility | None:
    with _singleton_lock:
        return _singleton


def jev_flags_transition(
    prior_home: Any,
    prior_away: Any,
    home: Any,
    away: Any,
) -> bool:
    """Mint-path hook: True only for a cached flag_veto on this pair."""
    sp = get_score_plausibility()
    if sp is None:
        return False
    try:
        return sp.veto_matches(prior_home, prior_away, home, away)
    except Exception:
        return False


def make_plausibility_from_config(
    config: Any, *, bus: Any = None, ask_fn: Any = None
) -> ScorePlausibility | None:
    enabled = bool(getattr(config, "enabled", False)) or _env_enabled()
    if not enabled:
        return None
    sp = ScorePlausibility(config, bus=bus, ask_fn=ask_fn)
    if not sp.enabled:
        return None
    global _singleton
    with _singleton_lock:
        _singleton = sp
    return sp
