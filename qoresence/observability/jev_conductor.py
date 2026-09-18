"""Jev conductor — TypeSafe replacement for ClutchBot/MatchAgent *semantics*.

Jev is text-only ([state](https://docs.typesafe.ai/concepts/state.md)): it cannot
see HDMI crops. Pixel → JSON stays on the VLM. This module replaces:

- ClutchBot Quicksilver *rewrite* with a **Choice** over closed chat templates
- MatchAgent muse-spark *generation* with a **Choice** over closed observe lines
- Scorebug *groundedness referee* (after VLM JSON harvest) with Nouls already
  on the Noul observatory

Code owns tickets, clocks, digits, clips, and bus emit. Jev never licenses
scores. Default OFF: ``--jev`` / ``QORESENCE_JEV=1``. ``--play`` does not enable.

API key: ``TYPESAFE_API_KEY`` or ``.secrets/typesafe.key`` (never log the value).
"""

from __future__ import annotations

import logging
import os
import re
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

FAST_ACTS = (
    "silent",
    "chat_red_zone",
    "chat_close_late",
    "chat_input_spike",
    "chat_clutch_window",
    "consider_clip",
    "arm_prediction",
)

OBSERVE_ACTS = (
    "silent",
    "unlabeled",
    "picture_hud",
    "board_licensed",
)

CHAT_TEMPLATES = {
    "chat_red_zone": "Red-zone energy spike — something's cooking.",
    "chat_close_late": "Late and tight — intensity is climbing.",
    "chat_input_spike": "Controller heat on a live drive — eyes up.",
    "chat_clutch_window": "Clutch window opening — pad and picture aligned.",
    "silent": "",
}

_SCORE_DIGIT_RE = re.compile(r"\b\d{1,2}\s*[-–—:]\s*\d{1,2}\b")
_SCORE_PAIR_RE = re.compile(r"(\d{1,2})\s*[-–—:]\s*(\d{1,2})")


def scoreline_matches_board(text: str | None, home: Any, away: Any) -> bool:
    """True when text carries no scoreline, or a scoreline matching the board.

    Deterministic — no model call. A stated pair that does not match
    home/away in either order fails (licensed-but-wrong guard).
    """
    pairs = [(int(a), int(b)) for a, b in _SCORE_PAIR_RE.findall(text or "")]
    if not pairs:
        return True
    try:
        h, a = int(home), int(away)
    except (TypeError, ValueError):
        return False
    return any(p == (h, a) or p == (a, h) for p in pairs)


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


def conductor_questions() -> dict[str, Any]:
    """One request: clutch act + match observe + speculative clip/arm.

    Question IDs are for code. Meaning lives in instructions.
    """
    try:
        from typesafe_sdk import Choice, Noul
    except Exception:
        return {}
    return {
        "fast_act": Choice(
            instructions={
                "question": (
                    "Given `coupling`, `situation`, and `policy`, which fast-path "
                    "act should fire? Select a closed template."
                ),
                "focus": "Classify the act, not whether tickets exist — code owns tickets.",
                "never": "Never invent scores. `silent` if quiet, menu, or no coupling ticket for heat.",
            },
            criteria={
                "silent": {"what": "No act.", "not_for": "Heat or join evidence worth soft chat."},
                "chat_red_zone": {"what": "Soft chat: red-zone energy.", "not_for": "Scorelines."},
                "chat_close_late": {"what": "Soft chat: late and close.", "not_for": "Scorelines."},
                "chat_input_spike": {"what": "Soft chat: pad energy on a live drive.", "not_for": "Menus or idle pads."},
                "chat_clutch_window": {"what": "Soft chat: pad and picture aligned in a clutch window.", "not_for": "Skill or highlight claims."},
                "consider_clip": {"what": "Local HDMI clip *consideration*.", "not_for": "A highlight claim."},
                "arm_prediction": {"what": "Arm a prediction latch.", "not_for": "Starting or resolving — confirm path owns that."},
            },
        ),
        "observe": Choice(
            instructions={
                "question": "Pick one match-observer sentence kind from `evidence`.",
                "focus": "Cite only that bag. `board_licensed` only if `evidence.board_locked` and a confirm ticket.",
                "never": "Never invent digits or button names.",
            },
            criteria={
                "silent": {"what": "Not enough licensed evidence to speak."},
                "unlabeled": {"what": "No picture HID and no confirm ticket."},
                "picture_hud": {"what": "Picture HID label is present.", "not_for": "A pad press — DualSense is not on this host."},
                "board_licensed": {"what": "Confirm ticket + locked board — code will fill digits."},
            },
        ),
        "consider_clip": Noul(
            instructions={
                "question": (
                    "Assuming a coupling ticket exists, is pad+picture dense "
                    "enough to *consider* a local HDMI clip?"
                ),
                "true": "High coupling with red-zone or late-close situation.",
                "false": "Idle, menu, or sparse input.",
                "never": "Not a highlight or clutch claim — observation only.",
            },
        ),
        "arm_prediction": Noul(
            instructions={
                "question": "Assuming red-zone coupling, should the prediction latch arm?",
                "true": "Red-zone + dense join; latch only.",
                "false": "Do not arm.",
                "never": "Confirm path still owns start/resolve.",
            },
        ),
    }


def fill_chat(act: str) -> str:
    text = CHAT_TEMPLATES.get(act, "")
    if not text:
        return ""
    return _SCORE_DIGIT_RE.sub("the scoreboard", text)


def fill_observe(act: str, evidence: dict[str, Any]) -> str:
    """Code fills the closed line. Digits only from the confirm ticket bag."""
    bag = evidence if isinstance(evidence, dict) else {}
    locked = bool(bag.get("board_locked") and bag.get("confirm_ticket_id"))
    pic = bag.get("picture_hid") if isinstance(bag.get("picture_hid"), dict) else None
    if act == "board_licensed" and locked:
        hs, aws = bag.get("home_score"), bag.get("away_score")
        if hs is None or aws is None:
            return "Board licensed."
        q = bag.get("quarter")
        qbit = f" Q{q}" if q not in (None, "") else ""
        return f"Board licensed {aws}-{hs}{qbit}."
    if act == "picture_hud" and pic and pic.get("hid_button"):
        return f"Picture HUD labeled {pic.get('hid_button')} — not a pad press."
    if act == "unlabeled":
        return "Unlabeled. Pad not on this host."
    return ""


def compose_conductor(
    *,
    fast_act: str | None = None,
    fast_confidence: float | None = None,
    observe: str | None = None,
    observe_confidence: float | None = None,
    clip_noul: float | None = None,
    arm_noul: float | None = None,
    coupling: float = 0.0,
    red_zone: bool = False,
    late_close: bool = False,
    heat_ticket: bool = False,
    board_locked: bool = False,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Code-owned policy. Low Choice confidence → silent. Tickets still gate."""
    act = fast_act if fast_act in FAST_ACTS else "silent"
    if fast_confidence is not None and fast_confidence < 0.5:
        act = "silent"
    obs = observe if observe in OBSERVE_ACTS else "silent"
    if observe_confidence is not None and observe_confidence < 0.5:
        obs = "silent"
    if obs == "board_licensed" and not board_locked:
        obs = "silent"

    chat_act = act if act.startswith("chat_") else None
    if chat_act and not heat_ticket and act != "chat_red_zone" and act != "chat_close_late":
        # input_spike / clutch_window need a coupling ticket (heat law)
        if act in {"chat_input_spike", "chat_clutch_window"} and not heat_ticket:
            chat_act = None
            if act != "consider_clip":
                act = "silent"

    clip_ok = (
        (act == "consider_clip" or (clip_noul is not None and clip_noul >= 0.7))
        and coupling >= 0.55
        and (red_zone or late_close)
    )
    arm_ok = (
        (act == "arm_prediction" or (arm_noul is not None and arm_noul >= 0.7))
        and red_zone
        and coupling >= 0.50
    )

    chat = fill_chat(chat_act) if chat_act else ""
    note = fill_observe(obs, evidence or {})

    # Licensed-but-wrong guard: a stated scoreline that does not match the
    # board goes blank (deterministic — no model call needed).
    ev = evidence if isinstance(evidence, dict) else {}
    digits_verified = True
    if chat and not scoreline_matches_board(chat, ev.get("home_score"), ev.get("away_score")):
        chat = ""
        digits_verified = False
    if note and not scoreline_matches_board(note, ev.get("home_score"), ev.get("away_score")):
        note = ""
        digits_verified = False

    return {
        "plane": PLANE,
        "fast_act": act,
        "fast_confidence": fast_confidence,
        "observe": obs,
        "observe_confidence": observe_confidence,
        "chat": chat,
        "observe_text": note,
        "may_consider_clip": bool(clip_ok),
        "may_arm": bool(arm_ok),
        "digits_verified": digits_verified,
        "licenses_digits": False,
        "source": "jev",
    }


def conductor_preflight(state: dict[str, Any]) -> dict[str, Any] | None:
    """Deterministic refuses before any model call. None → proceed."""
    ev = state.get("evidence") if isinstance(state.get("evidence"), dict) else {}
    draft = state.get("draft") if isinstance(state.get("draft"), dict) else {}
    blob = ev if ev else draft
    if any(
        blob.get(k)
        for k in ("truth_claim", "humanity_claim", "ban_claim", "eligibility_claim")
    ):
        out = compose_conductor()
        out["reason"] = "truth/humanity/ban claim refused at preflight"
        out["source"] = "preflight"
        return out
    return None


def local_heuristic_conductor(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in when SDK/key is absent."""
    sit = state.get("situation") if isinstance(state.get("situation"), dict) else {}
    ev = state.get("evidence") if isinstance(state.get("evidence"), dict) else {}
    coup = float(state.get("coupling") or sit.get("coupling") or 0.0)
    red = bool(state.get("red_zone") or sit.get("red_zone"))
    close = bool(state.get("close") or sit.get("close"))
    late = bool(state.get("late_close") or sit.get("late"))
    heat = bool(state.get("heat_ticket"))
    locked = bool(ev.get("board_locked") and ev.get("confirm_ticket_id"))
    pic = ev.get("picture_hid") if isinstance(ev.get("picture_hid"), dict) else None

    if red and (close or late) and heat:
        act, conf = "chat_clutch_window", 0.82
    elif red:
        act, conf = "chat_red_zone", 0.78
    elif close and late:
        act, conf = "chat_close_late", 0.76
    elif heat and coup >= 0.4:
        act, conf = "chat_input_spike", 0.72
    else:
        act, conf = "silent", 0.9

    if locked:
        obs, oconf = "board_licensed", 0.88
    elif pic and pic.get("hid_button"):
        obs, oconf = "picture_hud", 0.84
    else:
        obs, oconf = "unlabeled", 0.8

    clip = 0.8 if coup >= 0.55 and (red or (close and late)) else 0.15
    arm = 0.8 if red and coup >= 0.5 else 0.1
    return {
        "fast_act": act,
        "fast_confidence": conf,
        "observe": obs,
        "observe_confidence": oconf,
        "clip_noul": clip,
        "arm_noul": arm,
        "source": "local_heuristic",
    }


class JevConductor:
    """Optional TypeSafe client. Never called on the capture/bus thread."""

    def __init__(self, config: Any = None, ask_fn: Any = None) -> None:
        self.config = config
        self._ask_fn = ask_fn
        self._lock = threading.Lock()
        self._last: dict[str, Any] = {}
        self._last_ns = 0
        self._asked = 0
        self._warned_typesafe = [False]
        self._typesafe_timeout_s = float(
            getattr(config, "typesafe_timeout_s", DEFAULT_TIMEOUT_S) or DEFAULT_TIMEOUT_S
        ) if config is not None else DEFAULT_TIMEOUT_S
        self._ask_cadence = AskCadence(
            ask_interval_s=float(
                getattr(config, "ask_interval_s", DEFAULT_ASK_INTERVAL_S)
                or DEFAULT_ASK_INTERVAL_S
            ) if config is not None else DEFAULT_ASK_INTERVAL_S,
            warn_label="jev",
        )
        enabled = bool(getattr(config, "enabled", False)) if config is not None else False
        self.enabled = enabled or _env_enabled()

    def judge(self, state: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {
                "plane": PLANE,
                "fast_act": "silent",
                "observe": "silent",
                "chat": "",
                "observe_text": "",
                "may_consider_clip": False,
                "may_arm": False,
                "licenses_digits": False,
                "source": "off",
            }
        pre = conductor_preflight(state)
        if pre is not None:
            with self._lock:
                self._last = pre
                self._last_ns = time.monotonic_ns()
                self._asked += 1
            return pre
        answers = None
        if self._ask_fn is not None:
            answers = self._ask_fn(state)
        if answers is None:
            answers = self._ask_cadence.ask_or_reuse(
                lambda: self._try_typesafe(state)
            )
        if answers is None:
            answers = local_heuristic_conductor(state)
        ev = state.get("evidence") if isinstance(state.get("evidence"), dict) else {}
        composed = compose_conductor(
            fast_act=answers.get("fast_act"),
            fast_confidence=answers.get("fast_confidence"),
            observe=answers.get("observe"),
            observe_confidence=answers.get("observe_confidence"),
            clip_noul=answers.get("clip_noul"),
            arm_noul=answers.get("arm_noul"),
            coupling=float(state.get("coupling") or 0.0),
            red_zone=bool(state.get("red_zone")),
            late_close=bool(state.get("late_close")),
            heat_ticket=bool(state.get("heat_ticket")),
            board_locked=bool(ev.get("board_locked") and ev.get("confirm_ticket_id")),
            evidence=ev,
        )
        composed["source"] = answers.get("source") or composed.get("source") or "unknown"
        with self._lock:
            self._last = composed
            self._last_ns = time.monotonic_ns()
            self._asked += 1
        return composed

    def last(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            last = dict(self._last)
            asked = self._asked
            last_ns = self._last_ns
        age = None
        if last_ns:
            age = round((time.monotonic_ns() - last_ns) / 1e9, 3)
        return {
            "enabled": bool(self.enabled),
            "key_present": _key_present(),
            "asked": asked,
            "last_age_s": age,
            "fast_act": last.get("fast_act"),
            "observe": last.get("observe"),
            "licenses_digits": False,
            **self._ask_cadence.stats(),
            "replaces": ["clutchbot_llm", "match_agent_llm", "scorebug_referee"],
            "cannot_replace": ["hdmi_pixels", "tickets", "clocks"],
            "source": last.get("source"),
        }

    def _try_typesafe(self, state: dict[str, Any]) -> dict[str, Any] | None:
        questions = conductor_questions()
        if not questions:
            return None
        payload = {
            "policy": (
                "Observation only. Never license score digits. Never claim clutch "
                "as a highlight. DualSense stays on the PS5."
            ),
            "coupling": state.get("coupling"),
            "red_zone": state.get("red_zone"),
            "late_close": state.get("late_close"),
            "close": state.get("close"),
            "heat_ticket": state.get("heat_ticket"),
            "situation": state.get("situation") or {},
            "evidence": state.get("evidence") or {},
        }
        response = system_one(
            state=payload,
            questions=questions,
            timeout_s=self._typesafe_timeout_s,
            warn_label="jev",
            warned_flag=self._warned_typesafe,
            logger=log,
        )
        if response is None:
            return None
        choices = getattr(response, "choices", {}) or {}
        nouls = getattr(response, "nouls", {}) or {}
        fa = choices.get("fast_act")
        ob = choices.get("observe")
        cl = nouls.get("consider_clip")
        ar = nouls.get("arm_prediction")
        return {
            "fast_act": getattr(fa, "choice", None) if fa is not None else None,
            "fast_confidence": float(getattr(fa, "confidence", 0) or 0)
            if fa is not None
            else None,
            "observe": getattr(ob, "choice", None) if ob is not None else None,
            "observe_confidence": float(getattr(ob, "confidence", 0) or 0)
            if ob is not None
            else None,
            "clip_noul": float(cl.noul) if cl is not None else None,
            "arm_noul": float(ar.noul) if ar is not None else None,
            "source": "typesafe",
        }



_singleton: JevConductor | None = None
_singleton_lock = threading.Lock()


def get_jev_conductor() -> JevConductor | None:
    with _singleton_lock:
        return _singleton


def make_jev_from_config(config: Any) -> JevConductor | None:
    enabled = bool(getattr(config, "enabled", False)) or _env_enabled()
    if not enabled:
        return None
    cond = JevConductor(config)
    if not cond.enabled:
        return None
    global _singleton
    with _singleton_lock:
        _singleton = cond
    return cond
