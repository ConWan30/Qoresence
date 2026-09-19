"""Press labeler — Jev closes the fail-closed gap on laptop-HID pad presses.

Deterministic EA sheets already label ``button + mode → verb``
(``madden_controls`` / ``cfb_controls``). When ``mode`` is None (ambiguous
picture sheet) or a ``SheetConflict`` fires, every press in that window goes
**unlabeled** even when it clearly did something. This module is the
observation-plane referee for that gap.

Three outcomes per press, fail-closed — never a fourth:

- ``labeled``   — verb from the EA sheet (deterministic or Jev-picked mode)
- ``eaten``     — press observed, picture did not respond (lag, anim lock, menu)
- ``unlabeled`` — no evidence either way

Two passes per press. The wire label is provisional — ``eaten`` may not fire
without after-evidence. A worker then samples the first post-press
``visual_phase`` (the next VisualContext produced at least ~0.4s after the
edge) and re-judges with real after-state: ``eaten`` means *observed*
non-response, and a missing post-press sample stays ``unlabeled``.

Code owns HID sampling, the seq join, the EA sheet, and all defaults. Jev
never sees raw HID reports or pixels — it judges the joined record. Never
licenses score digits, never claims skill, never calls a press a console
fault ("eaten" is an observation, not a hardware verdict).

Gated by the same flag as the Jev conductor: ``--jev`` / ``QORESENCE_JEV=1``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from qoresence.observability.typesafe_ask import (
    DEFAULT_TIMEOUT_S,
    system_one,
)

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"

def _note_ledger(pack: str, verdict: dict, **kw) -> None:
    try:
        from qoresence.agents.society.judgment_ledger import note_pack_verdict

        note_pack_verdict(pack, verdict, **kw)
    except Exception:
        pass


OUTCOMES = ("labeled", "unlabeled", "eaten")
CONFLICT_PICKS = ("picture", "pad", "lag", "unresolvable")
NO_MATCH = "no_match"

# Efficacy thresholds — Noul ~0.5 is a coin-flip, not medium intensity.
EFFICACY_RESPONDED = 0.6
EFFICACY_EATEN = 0.3

# Post-press phase sampling. A press-time wire only carries the *before*
# picture; "eaten" needs an *after* observation. The visual lobe produces a
# new VisualContext roughly once a second (frame_sample_rate 30 @ ~30fps), so
# a verdict waits for the first context produced at least AFTER_DELAY_S after
# the edge, then re-judges with real after-evidence.
AFTER_DELAY_S = 0.4
AFTER_TIMEOUT_S = 4.0
AFTER_POLL_S = 0.1
AFTER_QUEUE_MAX = 64


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_JEV", "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }


def _key_present() -> bool:
    if os.environ.get("TYPESAFE_API_KEY", "").strip():
        return True
    p = Path(".secrets/typesafe.key")
    try:
        return p.is_file() and bool(p.stat().st_size)
    except Exception:
        return False


def press_questions(candidate_modes: list[str]) -> dict[str, Any]:
    """Fan-out for one press: mode pick + efficacy + conflict pick.

    ``candidate_modes`` come from the EA sheet's own mode keys — Jev cannot
    choose a mode the code did not offer. ``no_match`` stays in the set.
    """
    try:
        from typesafe_sdk import Choice, Noul
    except Exception:
        return {}

    mode_criteria = {
        m: {"what": f"Observed picture state matches the {m} control sheet."}
        for m in candidate_modes
    }
    mode_criteria[NO_MATCH] = {
        "what": "No candidate sheet fits; stay unlabeled.",
        "not_for": "A guess — pick this whenever the picture is ambiguous.",
    }
    return {
        "mode_pick": Choice(
            instructions={
                "question": (
                    "`press` is a real DualSense edge on the laptop HID, and "
                    "`picture` is what HDMI showed around `press.frame_seq`. "
                    "Which control sheet was active?"
                ),
                "focus": "Classify the mode only — code re-resolves the verb through the EA sheet.",
                "never": "Pick no_match if the picture does not fit any candidate.",
            },
            criteria=mode_criteria,
        ),
        "press_efficacy": Noul(
            instructions={
                "question": (
                    "Did the picture respond to `press`? Compare "
                    "`picture.phase_before` with `picture.phase_after`."
                ),
                "true": "Picture state changed in a way consistent with the press — phase change, play start, or menu advance.",
                "false": "Picture did not respond — same phase, no action.",
                "never": "Not a lag or hardware verdict — observation only.",
            },
        ),
        "conflict_pick": Choice(
            instructions={
                "question": (
                    "`conflict` says the picture sheet and pad sheet disagree. "
                    "Which side does the joined evidence favor?"
                ),
                "focus": "Pick lag when timing desync explains it; unresolvable when neither side wins.",
                "never": "Never claim the game or controller failed.",
            },
            criteria={
                "picture": {"what": "Picture sheet matches observed state; pad label was wrong."},
                "pad": {"what": "Pad sheet matches observed state; picture label was stale."},
                "lag": {"what": "Sheets disagree because of input/video desync."},
                "unresolvable": {"what": "Cannot tell — keep the press unlabeled."},
            },
        ),
    }


def compose_press_label(
    *,
    hid_button: str,
    frame_seq: int | None = None,
    clock_ns: int | None = None,
    verb: str | None = None,
    mode: str | None = None,
    picked_mode: str | None = None,
    picked_verb: str | None = None,
    mode_confidence: float | None = None,
    efficacy_noul: float | None = None,
    conflict: dict[str, Any] | None = None,
    conflict_pick: str | None = None,
    conflict_confidence: float | None = None,
    has_after_evidence: bool = False,
) -> dict[str, Any]:
    """Code-owned composition. Fail closed: ambiguous → unlabeled.

    ``picked_verb`` is the EA-sheet verb the *caller* resolved after Jev picked
    a mode — Jev never emits a verb string itself.
    """
    conf_res = (
        conflict_pick
        if conflict is not None
        and conflict_pick in CONFLICT_PICKS
        and (conflict_confidence is None or conflict_confidence >= 0.5)
        else None
    )

    label = None
    label_source = None
    effective_mode = mode
    if conf_res == "picture" and isinstance(conflict, dict):
        effective_mode = conflict.get("picture_sheet") or mode
        label_source = "conflict_picture" if picked_verb else None
        label = picked_verb
        if picked_verb:
            effective_mode = picked_mode or effective_mode
    elif verb:
        label = verb
        label_source = "sheet"
    elif picked_verb:
        label = picked_verb
        label_source = "jev_mode_pick"
        effective_mode = picked_mode

    # Efficacy gates the outcome; it never invents a label.
    # Eaten claims the picture was *observed* not responding — requires real
    # after-evidence. Missing after-state is unlabeled, not eaten.
    responded = efficacy_noul is not None and efficacy_noul >= EFFICACY_RESPONDED
    eaten = (
        has_after_evidence
        and efficacy_noul is not None
        and efficacy_noul <= EFFICACY_EATEN
    )

    if eaten and conf_res not in {"lag"}:
        outcome = "eaten"
    elif label:
        outcome = "labeled"
    else:
        outcome = "unlabeled"

    gamer = ""
    if outcome == "labeled" and label:
        gamer = f"{hid_button} — {label}"
    elif outcome == "eaten":
        gamer = f"{hid_button} — no picture response"

    return {
        "plane": PLANE,
        "hid_button": hid_button,
        "frame_seq": frame_seq,
        "clock_ns": clock_ns,
        "label": label,
        "outcome": outcome,
        "mode": effective_mode,
        "label_source": label_source,
        "conflict_resolution": conf_res,
        "efficacy_noul": efficacy_noul,
        "responded": bool(responded),
        "gamer": gamer,
        "licenses_digits": False,
    }


def _ctx_latency_s(ctx_obj: Any) -> float:
    """Analysis latency of a VisualContext in seconds (0 when unknown)."""
    try:
        if isinstance(ctx_obj, dict):
            ms = ctx_obj.get("latency_ms")
        else:
            ms = getattr(ctx_obj, "latency_ms", None)
        return min(max(float(ms or 0.0), 0.0), 2000.0) / 1000.0
    except Exception:
        return 0.0


def _phase_from_context(ctx_obj: Any) -> str | None:
    """visual_phase out of a VisualContext/dict (same coercion as the wire)."""
    if ctx_obj is None:
        return None
    try:
        if hasattr(ctx_obj, "to_dict"):
            d = ctx_obj.to_dict()
        elif isinstance(ctx_obj, dict):
            d = ctx_obj
        elif hasattr(ctx_obj, "__dict__"):
            d = ctx_obj.__dict__
        else:
            return None
        from qoresence.observation.sheet_from_picture import get_visual_phase_from_context

        return get_visual_phase_from_context(d)
    except Exception:
        return None


def local_press_labels(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in — identical to today's behavior, plus efficacy.

    Never upgrades unlabeled → labeled; only the real Jev path may do that.
    """
    obs = state.get("obs") if isinstance(state.get("obs"), dict) else {}
    picture = state.get("picture") if isinstance(state.get("picture"), dict) else {}
    conflict = state.get("conflict") if isinstance(state.get("conflict"), dict) else None

    before = picture.get("phase_before")
    after = picture.get("phase_after")
    if after is None:
        efficacy = 0.5
    elif before is None or after != before:
        efficacy = 0.75
    else:
        efficacy = 0.2

    conflict_pick = None
    conflict_conf = None
    if conflict:
        if conflict.get("kind") == "lag" or conflict.get("reason") and "lag" in str(conflict.get("reason")).lower():
            conflict_pick, conflict_conf = "lag", 0.8
        else:
            conflict_pick, conflict_conf = "unresolvable", 0.7

    return {
        "mode_pick": NO_MATCH,
        "mode_confidence": 0.9,
        "efficacy_noul": efficacy,
        "conflict_pick": conflict_pick,
        "conflict_confidence": conflict_conf,
        "verb": obs.get("verb"),
        "mode": obs.get("mode"),
        "source": "local_heuristic",
    }


class PressLabeler:
    """Optional TypeSafe client. Never called on the capture/bus thread.

    Post-press verdicts run on a private worker thread: each wire label that
    had no ``phase_after`` is queued, and once the visual lobe has produced a
    fresh context (>= AFTER_DELAY_S after the edge) the judgment is re-run
    with real after-evidence. The provisional wire outcome is never mutated —
    the verdict is a second record (``verdict: True``) carried on later wires,
    JSONL, and ``stats()``. Worker never emits bus events (same class as the
    Noul observatory's rules).
    """

    def __init__(
        self,
        config: Any = None,
        ask_fn: Any = None,
        context_fn: Any = None,
        after_delay_s: float = AFTER_DELAY_S,
        after_timeout_s: float = AFTER_TIMEOUT_S,
        after_poll_s: float = AFTER_POLL_S,
    ) -> None:
        self.config = config
        self._ask_fn = ask_fn
        self._context_fn = context_fn
        self._after_delay_s = float(after_delay_s)
        self._after_timeout_s = float(after_timeout_s)
        self._after_poll_s = float(after_poll_s)
        self._lock = threading.Lock()
        self._asked = 0
        self._counts = {"labeled": 0, "unlabeled": 0, "eaten": 0}
        self._last_ns = 0
        # Post-press verdict state
        self._pending: list[dict[str, Any]] = []
        self._pending_keys: set[tuple] = set()
        self._work_evt = threading.Event()
        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None
        self._recent_verdicts: deque[dict[str, Any]] = deque(maxlen=8)
        self._last_verdict: dict[str, Any] = {}
        self._verdict_counts = {"labeled": 0, "unlabeled": 0, "eaten": 0}
        self._verdicts_done = 0
        self._after_sampled = 0
        self._after_timeout = 0
        self._after_dropped = 0
        self._jsonl_handle: Any = None
        self._jsonl_tried = False
        enabled = bool(getattr(config, "enabled", False)) if config is not None else False
        self.enabled = enabled or _env_enabled()
        self._warned_typesafe = [False]
        _cfg = config
        self._typesafe_timeout_s = float(
            (getattr(_cfg, "typesafe_timeout_s", DEFAULT_TIMEOUT_S) if _cfg is not None else DEFAULT_TIMEOUT_S)
            or DEFAULT_TIMEOUT_S
        )

    def label_press(
        self,
        obs: Any,
        *,
        context: dict[str, Any] | None = None,
        lookup: Any = None,
    ) -> dict[str, Any]:
        """Label one ControlObservation/dict. Off → deterministic outcome only."""
        od = self._obs_dict(obs)
        ctx = dict(context or {})
        button = str(od.get("hid_button") or "")

        if not self.enabled:
            out = compose_press_label(
                hid_button=button,
                frame_seq=od.get("frame_seq"),
                clock_ns=od.get("clock_ns"),
                verb=od.get("verb"),
                mode=od.get("mode"),
                conflict=ctx.get("conflict"),
            )
            out["source"] = "off"
            return out

        # Preflight: deterministic sheet label with no conflict and no
        # phase_after to judge needs no model call.
        if od.get("verb") and not ctx.get("conflict") and ctx.get("phase_after") is None:
            out = compose_press_label(
                hid_button=button,
                frame_seq=od.get("frame_seq"),
                clock_ns=od.get("clock_ns"),
                verb=od["verb"],
                mode=od.get("mode"),
            )
            out["source"] = "preflight"
            with self._lock:
                self._asked += 1
                self._last_ns = time.monotonic_ns()
                self._counts["labeled"] += 1
            self._enqueue_after(od, ctx, lookup, out)
            return out

        out = self._judge(od, ctx, lookup)

        with self._lock:
            self._asked += 1
            self._last_ns = time.monotonic_ns()
            if out["outcome"] in self._counts:
                self._counts[out["outcome"]] += 1

        # Provisional wire labels lack after-evidence — queue the deferred
        # verdict so "eaten" means *observed* non-response, not missing state.
        if ctx.get("phase_after") is None:
            self._enqueue_after(od, ctx, lookup, out)
        return out

    def _judge(
        self,
        od: dict[str, Any],
        ctx: dict[str, Any],
        lookup: Any = None,
    ) -> dict[str, Any]:
        """Ask chain + composition for one press. Runs on caller or worker."""
        button = str(od.get("hid_button") or "")
        state = {
            "press": {
                "hid_button": button,
                "frame_seq": od.get("frame_seq"),
                "clock_ns": od.get("clock_ns"),
            },
            "obs": {"verb": od.get("verb"), "mode": od.get("mode")},
            "picture": {
                "phase_before": ctx.get("phase_before") or ctx.get("visual_phase"),
                "phase_after": ctx.get("phase_after"),
                "picture_sheet": ctx.get("picture_sheet"),
            },
            "conflict": ctx.get("conflict"),
            "candidate_modes": list(ctx.get("candidate_modes") or []),
            "situation": ctx.get("situation") or {},
        }

        answers = None
        if self._ask_fn is not None:
            answers = self._ask_fn(state)
        if answers is None:
            answers = self._try_typesafe(state)
        if answers is None:
            answers = local_press_labels(state)

        # Code resolves a Jev-picked mode back through the EA sheet.
        picked_mode = answers.get("mode_pick")
        mode_conf = answers.get("mode_confidence")
        picked_verb = None
        if (
            picked_mode
            and picked_mode != NO_MATCH
            and picked_mode in state["candidate_modes"]
            and (mode_conf is None or mode_conf >= 0.5)
            and lookup is not None
        ):
            try:
                picked_verb = lookup.lookup_verb(button, picked_mode)
            except Exception:
                picked_verb = None

        # Conflict resolved to "picture" — re-run lookup on the picture sheet.
        conf_pick = answers.get("conflict_pick")
        if conf_pick == "picture" and lookup is not None and isinstance(ctx.get("conflict"), dict):
            ps = ctx["conflict"].get("picture_sheet")
            if ps:
                try:
                    pv = lookup.lookup_verb(button, ps)
                    if pv:
                        picked_mode = ps
                        picked_verb = pv
                except Exception:
                    pass

        out = compose_press_label(
            hid_button=button,
            frame_seq=od.get("frame_seq"),
            clock_ns=od.get("clock_ns"),
            verb=answers.get("verb") if answers.get("verb") is not None else od.get("verb"),
            mode=od.get("mode") if conf_pick != "picture" else None,
            picked_mode=picked_mode,
            picked_verb=picked_verb,
            mode_confidence=mode_conf,
            efficacy_noul=answers.get("efficacy_noul"),
            conflict=ctx.get("conflict"),
            conflict_pick=conf_pick,
            conflict_confidence=answers.get("conflict_confidence"),
            has_after_evidence=ctx.get("phase_after") is not None,
        )
        out["source"] = answers.get("source") or "unknown"
        return out

    # ── Post-press phase sampling (after-evidence verdicts) ──────────────

    def _enqueue_after(
        self,
        od: dict[str, Any],
        ctx: dict[str, Any],
        lookup: Any,
        provisional: dict[str, Any],
    ) -> None:
        key = (od.get("clock_ns"), od.get("frame_seq"), str(od.get("hid_button") or ""))
        job = {
            "key": key,
            "od": dict(od),
            "ctx": dict(ctx),
            "lookup": lookup,
            "provisional": dict(provisional),
            "press_mono": time.monotonic(),
            "deadline": time.monotonic() + self._after_delay_s,
        }
        with self._lock:
            if key in self._pending_keys:
                return
            if len(self._pending) >= AFTER_QUEUE_MAX:
                old = self._pending.pop(0)
                self._pending_keys.discard(old["key"])
                self._after_dropped += 1
            self._pending.append(job)
            self._pending_keys.add(key)
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._after_loop, name="press-labeler-after", daemon=True
                )
                self._worker.start()
        self._work_evt.set()

    def _after_loop(self) -> None:
        """Wait for post-press contexts, then re-judge with real after-state."""
        while not self._stop_evt.is_set():
            with self._lock:
                pending = list(self._pending)
            if not pending:
                self._work_evt.wait(0.25)
                self._work_evt.clear()
                continue
            now = time.monotonic()
            earliest = min(j["deadline"] for j in pending)
            if earliest > now:
                self._work_evt.wait(min(earliest - now, 0.5))
                self._work_evt.clear()
                continue
            # Wait for a context produced after the earliest due deadline —
            # that is the first sample guaranteed to post-date the press's
            # response window for every job we drain below.
            budget = min(
                j["press_mono"] + self._after_timeout_s for j in pending
            ) - now
            ctx_obj, frame_time = self._await_fresh_context(max(budget, 0.05))
            if ctx_obj is not None:
                phase_after = _phase_from_context(ctx_obj)
                with self._lock:
                    due = [j for j in self._pending if j["deadline"] <= frame_time]
                    for j in due:
                        self._pending.remove(j)
                        self._pending_keys.discard(j["key"])
            else:
                phase_after = None
                with self._lock:
                    due = [
                        j
                        for j in self._pending
                        if j["press_mono"] + self._after_timeout_s <= time.monotonic()
                    ]
                    for j in due:
                        self._pending.remove(j)
                        self._pending_keys.discard(j["key"])
            for job in due:
                try:
                    self._finish_after(job, phase_after)
                except Exception as e:
                    log.debug("press verdict skipped: %s", e)

    def _current_context(self) -> Any:
        if self._context_fn is not None:
            try:
                return self._context_fn()
            except Exception:
                return None
        try:
            from qoresence.lobes.visual import get_last_visual_context

            return get_last_visual_context()
        except Exception:
            return None

    def _await_fresh_context(self, budget_s: float) -> tuple[Any, float]:
        """Poll until a *new* context object exists or budget runs out.

        Returns ``(context, frame_time_est)`` — the estimated monotonic time
        the analyzed frame was captured, i.e. first-seen minus analysis
        latency. A cloud-VLM context first observed at T can describe a frame
        from T-2s; without the correction "after" samples would silently
        pre-date the response window.
        """
        baseline = self._current_context()
        deadline = time.monotonic() + max(budget_s, 0.0)
        while not self._stop_evt.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, 0.0
            self._stop_evt.wait(min(self._after_poll_s, remaining))
            ctx = self._current_context()
            if ctx is not None and ctx is not baseline:
                latency_s = _ctx_latency_s(ctx)
                frame_time = time.monotonic() - latency_s - self._after_poll_s
                return ctx, frame_time
        return None, 0.0

    def _finish_after(self, job: dict[str, Any], phase_after: str | None) -> None:
        if phase_after is None:
            # No fresh context inside the window — no model call needed to say
            # "still no evidence". Verdict echoes the provisional outcome.
            verdict = dict(job["provisional"])
            verdict["verdict"] = True
            verdict["phase_after"] = None
            verdict["after_timeout"] = True
        else:
            ctx = dict(job["ctx"])
            ctx["phase_after"] = phase_after
            verdict = self._judge(job["od"], ctx, job["lookup"])
            verdict["verdict"] = True
            verdict["phase_after"] = phase_after
        verdict["after_age_s"] = round(time.monotonic() - job["press_mono"], 3)
        verdict["provisional"] = {
            k: job["provisional"].get(k)
            for k in ("outcome", "label", "mode", "source")
        }
        slim = {
            "outcome": verdict.get("outcome"),
            "label": verdict.get("label"),
            "hid_button": verdict.get("hid_button"),
            "frame_seq": verdict.get("frame_seq"),
            "efficacy_noul": verdict.get("efficacy_noul"),
            "responded": verdict.get("responded"),
            "phase_after": phase_after,
            "source": verdict.get("source"),
        }
        with self._lock:
            self._verdicts_done += 1
            if phase_after is not None:
                self._after_sampled += 1
            else:
                self._after_timeout += 1
            if verdict.get("outcome") in self._verdict_counts:
                self._verdict_counts[verdict["outcome"]] += 1
            self._last_verdict = slim
            self._recent_verdicts.append(verdict)
        self._write_jsonl("press_verdict", verdict)
        _note_ledger(
            "press",
            verdict,
            clock_ns=verdict.get("clock_ns"),
            frame_seq=verdict.get("frame_seq"),
        )

    def drain_verdicts(self) -> list[dict[str, Any]]:
        """Pop completed verdicts so a later wire can carry them."""
        with self._lock:
            out = list(self._recent_verdicts)
            self._recent_verdicts.clear()
        return out

    def _write_jsonl(self, kind: str, rec: dict[str, Any]) -> None:
        try:
            if self._jsonl_handle is None and not self._jsonl_tried:
                self._jsonl_tried = True
                out_dir = Path("logs/press_labels")
                out_dir.mkdir(parents=True, exist_ok=True)
                self._jsonl_handle = (out_dir / "press_labels.jsonl").open(
                    "a", encoding="utf-8"
                )
            if self._jsonl_handle is None:
                return
            line = {"ts_ns": time.time_ns(), "kind": kind, **rec}
            self._jsonl_handle.write(json.dumps(line, default=str) + "\n")
            self._jsonl_handle.flush()
        except Exception:
            pass

    def stop(self) -> None:
        self._stop_evt.set()
        self._work_evt.set()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=2.0)
        try:
            if self._jsonl_handle is not None:
                self._jsonl_handle.close()
        except Exception:
            pass
        self._jsonl_handle = None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            asked = self._asked
            counts = dict(self._counts)
            last_ns = self._last_ns
            verdicts = dict(self._verdict_counts)
            verdicts["total"] = self._verdicts_done
            after = {
                "pending": len(self._pending),
                "sampled": self._after_sampled,
                "timeout": self._after_timeout,
                "dropped": self._after_dropped,
            }
            last_verdict = dict(self._last_verdict)
        return {
            "enabled": bool(self.enabled),
            "key_present": _key_present(),
            "asked": asked,
            "labeled": counts["labeled"],
            "unlabeled": counts["unlabeled"],
            "eaten": counts["eaten"],
            "last_age_s": round((time.monotonic_ns() - last_ns) / 1e9, 3) if last_ns else None,
            "verdicts": verdicts,
            "after": after,
            "last_verdict": last_verdict or None,
            "licenses_digits": False,
        }

    @staticmethod
    def _obs_dict(obs: Any) -> dict[str, Any]:
        if isinstance(obs, dict):
            return obs
        if hasattr(obs, "to_dict"):
            try:
                return obs.to_dict()
            except Exception:
                pass
        return {
            "frame_seq": getattr(obs, "frame_seq", None),
            "clock_ns": getattr(obs, "clock_ns", None),
            "hid_button": getattr(obs, "hid_button", None),
            "verb": getattr(obs, "verb", None),
            "mode": getattr(obs, "mode", None),
        }

    def _try_typesafe(self, state: dict[str, Any]) -> dict[str, Any] | None:
        questions = press_questions(state["candidate_modes"])
        if not questions:
            return None
        if not os.environ.get("TYPESAFE_API_KEY", "").strip():
            try:
                raw = Path(".secrets/typesafe.key").read_text(encoding="utf-8-sig").strip()
                if raw:
                    os.environ["TYPESAFE_API_KEY"] = raw
            except Exception:
                return None
        payload = {
            "policy": (
                "Observation only. Never license score digits, never claim "
                "skill, never call a press a console fault. Eaten means the "
                "picture did not respond — lag, animation lock, or menu."
            ),
            "press": state["press"],
            "picture": state["picture"],
            "conflict": state["conflict"],
            "situation": state["situation"],
        }
        response = system_one(
            state=payload,
            questions=questions,
            timeout_s=self._typesafe_timeout_s,
            warn_label="press_labeler",
            warned_flag=self._warned_typesafe,
            logger=log,
        )
        if response is None:
            return None
        choices = getattr(response, "choices", {}) or {}
        nouls = getattr(response, "nouls", {}) or {}
        mp = choices.get("mode_pick")
        cp = choices.get("conflict_pick")
        pe = nouls.get("press_efficacy")
        return {
            "mode_pick": getattr(mp, "choice", None) if mp is not None else None,
            "mode_confidence": float(getattr(mp, "confidence", 0) or 0) if mp is not None else None,
            "conflict_pick": getattr(cp, "choice", None) if cp is not None else None,
            "conflict_confidence": float(getattr(cp, "confidence", 0) or 0) if cp is not None else None,
            "efficacy_noul": float(pe.noul) if pe is not None else None,
            "source": "typesafe",
        }

_singleton: PressLabeler | None = None
_singleton_lock = threading.Lock()


def get_press_labeler() -> PressLabeler | None:
    with _singleton_lock:
        return _singleton


def make_press_labeler_from_config(config: Any) -> PressLabeler | None:
    enabled = bool(getattr(config, "enabled", False)) or _env_enabled()
    if not enabled:
        return None
    lab = PressLabeler(config)
    if not lab.enabled:
        return None
    global _singleton
    with _singleton_lock:
        _singleton = lab
    return lab


def label_wire_press(wire: dict[str, Any], *, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Attach a press label to an observation-wire dict. No-op when off.

    Returns the label dict or None — the wire is never mutated when the
    labeler is disabled or missing.
    """
    lab = get_press_labeler()
    if lab is None or not lab.enabled or not isinstance(wire, dict):
        return None
    button = wire.get("hid_button")
    if not button:
        return None
    lookup = None
    candidates: list[str] = []
    gp = str(wire.get("game_profile") or "").lower()
    try:
        if "madden" in gp:
            from qoresence.observation.madden_controls import get_madden_lookup

            lookup = get_madden_lookup()
        elif any(x in gp for x in ("cfb", "college", "ncaa")):
            from qoresence.observation.cfb_controls import CfbControlLookup

            lookup = CfbControlLookup()
        if lookup is not None:
            candidates = list(getattr(lookup, "_controls", {}) or [])
    except Exception:
        lookup = None
    ctx = dict(context or {})
    ctx.setdefault("visual_phase", wire.get("visual_phase"))
    ctx.setdefault("conflict", wire.get("conflict"))
    ctx["candidate_modes"] = candidates
    plabel = lab.label_press(wire, context=ctx, lookup=lookup)
    # Verdicts for earlier presses ride the next wire that exists.
    try:
        verdicts = lab.drain_verdicts()
        if verdicts:
            wire["press_verdicts"] = verdicts
    except Exception:
        pass
    return plabel
