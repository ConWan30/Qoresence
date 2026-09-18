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

Code owns HID sampling, the seq join, the EA sheet, and all defaults. Jev
never sees raw HID reports or pixels — it judges the joined record. Never
licenses score digits, never claims skill, never calls a press a console
fault ("eaten" is an observation, not a hardware verdict).

Gated by the same flag as the Jev conductor: ``--jev`` / ``QORESENCE_JEV=1``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"

OUTCOMES = ("labeled", "unlabeled", "eaten")
CONFLICT_PICKS = ("picture", "pad", "lag", "unresolvable")
NO_MATCH = "no_match"

# Efficacy thresholds — Noul ~0.5 is a coin-flip, not medium intensity.
EFFICACY_RESPONDED = 0.6
EFFICACY_EATEN = 0.3


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
    """Optional TypeSafe client. Never called on the capture/bus thread."""

    def __init__(self, config: Any = None, ask_fn: Any = None) -> None:
        self.config = config
        self._ask_fn = ask_fn
        self._lock = threading.Lock()
        self._asked = 0
        self._counts = {"labeled": 0, "unlabeled": 0, "eaten": 0}
        self._last_ns = 0
        enabled = bool(getattr(config, "enabled", False)) if config is not None else False
        self.enabled = enabled or _env_enabled()

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
            return out

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

        with self._lock:
            self._asked += 1
            self._last_ns = time.monotonic_ns()
            if out["outcome"] in self._counts:
                self._counts[out["outcome"]] += 1
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            asked = self._asked
            counts = dict(self._counts)
            last_ns = self._last_ns
        return {
            "enabled": bool(self.enabled),
            "key_present": _key_present(),
            "asked": asked,
            "labeled": counts["labeled"],
            "unlabeled": counts["unlabeled"],
            "eaten": counts["eaten"],
            "last_age_s": round((time.monotonic_ns() - last_ns) / 1e9, 3) if last_ns else None,
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
        if not _key_present():
            return None
        try:
            from typesafe_sdk import TypeSafeClient
        except Exception:
            return None
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
        try:
            with TypeSafeClient() as client:
                response = client.system_one(state=payload, questions=questions)
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
        except Exception as e:
            log.debug("press labeler system_one failed: %s", e)
            return None


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
    return lab.label_press(wire, context=ctx, lookup=lookup)
