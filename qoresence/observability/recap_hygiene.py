"""Recap envelope hygiene — observation door, never a seal.

Code owns join keys (clock, tickets, hashes). Jev may judge *language*
against the envelope. Unlocked digits, DualSense-as-failure, and truth
dests fail closed. Default OFF for TypeSafe; deterministic checks always run.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"
TRUTH_DEST_RE = re.compile(r"qortroller|poac|(?:^|[\s_\-])truth(?:$|[\s_\-])", re.I)
SCORE_PAIR_RE = re.compile(r"\b\d{1,2}\s*[-–—]\s*\d{1,2}\b")

ISSUE_KINDS = (
    "no_match",
    "situation_shift",
    "ungrounded_board",
    "empty_hid_success",
    "digit_leak",
    "truth_dest",
)


def _env_jev() -> bool:
    return os.environ.get("QORESENCE_JEV", "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }


def unlocked_digit_leak(envelope: dict[str, Any]) -> bool:
    """True when score-like digits appear without score_vlm_locked."""
    ticks = envelope.get("ticks") if isinstance(envelope.get("ticks"), list) else []
    for t in ticks:
        if not isinstance(t, dict):
            continue
        digits = t.get("score_digits")
        locked = bool(t.get("score_vlm_locked"))
        if digits not in (None, "", "□–□", "□-□") and not locked:
            return True
        if not locked:
            blob = str(digits or "") + str(t.get("text") or "")
            if SCORE_PAIR_RE.search(blob):
                return True
    extras = envelope.get("extras") if isinstance(envelope.get("extras"), dict) else {}
    door = envelope.get("door") if isinstance(envelope.get("door"), dict) else {}
    for blob in (extras, door, envelope.get("notary") or {}):
        if not isinstance(blob, dict):
            continue
        text = " ".join(str(v) for v in blob.values() if isinstance(v, str))
        if SCORE_PAIR_RE.search(text) and not envelope.get("board_locked"):
            return True
    return False


def dualsense_treated_as_failure(envelope: dict[str, Any]) -> bool:
    hid = envelope.get("hid_on_console")
    if hid is True:
        return False
    copy = " ".join(
        str(x)
        for x in (
            (envelope.get("door") or {}).get("copy") if isinstance(envelope.get("door"), dict) else "",
            envelope.get("body_reason"),
            envelope.get("pad_status"),
        )
        if x
    ).lower()
    return any(tok in copy for tok in ("pad wait", "pad_wait", "no controller", "hid failed"))


def truth_dest_named(envelope: dict[str, Any]) -> bool:
    wrap = envelope.get("wrap") if isinstance(envelope.get("wrap"), dict) else {}
    dest = str(envelope.get("dest_plane") or wrap.get("dest") or wrap.get("dest_plane") or "")
    return bool(dest and TRUTH_DEST_RE.search(dest))


def hygiene_questions() -> dict[str, Any]:
    try:
        from typesafe_sdk import Choice, Noul
    except Exception:
        return {}
    return {
        "digit_leak": Noul(
            instructions={
                "question": (
                    "Does this envelope paint score digits that are not under "
                    "`score_vlm_locked` plus a confirm ticket?"
                ),
                "true": "Unlocked or last-good digits appear.",
                "false": "Digits absent or locked with confirm ticket.",
                "never": "Observation law: blank is always safe — this is a leak check, not a digit check.",
            },
        ),
        "hid_failure_lie": Noul(
            instructions={
                "question": (
                    "Does the envelope treat DualSense-on-the-PS5 (empty laptop "
                    "HID) as a failure such as PAD WAIT?"
                ),
                "true": "Empty HID is called failure.",
                "false": "Empty HID is success or unmentioned.",
            },
        ),
        "citation": Choice(
            instructions={
                "question": (
                    "Do Recap claims about scores/presses match the ticks "
                    "(clock_ns + ticket_id)?"
                ),
                "focus": "Select relation to evidence — do not judge claim quality.",
                "never": "says_nothing when no score/press claim exists.",
            },
            criteria={
                "supports": {"what": "Claims cite locked ticks."},
                "contradicts": {"what": "Claims invent digits or presses.", "not_for": "A missing-but-unclaimed field."},
                "says_nothing": {"what": "No score/press claim."},
            },
        ),
        "issue_kind": Choice(
            instructions={
                "question": "If QorAct filed an issue from this Recap, which closed kind?",
                "never": "no_match when nothing is worth filing.",
            },
            criteria={
                "no_match": {"what": "Nothing to file."},
                "situation_shift": {"what": "Licensed board/situation change."},
                "ungrounded_board": {"what": "Parse looked like a plate / ungrounded."},
                "empty_hid_success": {"what": "DualSense stayed on the PS5."},
                "digit_leak": {"what": "Unlocked digits would have exported."},
                "truth_dest": {"what": "Wrap dest names qortroller/poac/truth."},
            },
        ),
    }


def compose_hygiene(
    envelope: dict[str, Any],
    *,
    digit_leak_noul: float | None = None,
    hid_fail_noul: float | None = None,
    citation: str | None = None,
    citation_confidence: float | None = None,
    issue_kind: str | None = None,
) -> dict[str, Any]:
    leak = unlocked_digit_leak(envelope)
    hid_lie = dualsense_treated_as_failure(envelope)
    truth = truth_dest_named(envelope)
    if digit_leak_noul is not None and digit_leak_noul >= 0.7:
        leak = True
    if hid_fail_noul is not None and hid_fail_noul >= 0.7:
        hid_lie = True
    cite = citation if citation in {"supports", "contradicts", "says_nothing"} else None
    if citation_confidence is not None and citation_confidence < 0.5:
        cite = None
    kind = issue_kind if issue_kind in ISSUE_KINDS else "no_match"
    if leak:
        kind = "digit_leak"
    elif truth:
        kind = "truth_dest"
    elif hid_lie:
        kind = "empty_hid_success"
    hold = leak or truth or hid_lie or cite == "contradicts"
    return {
        "plane": PLANE,
        "ok": not hold,
        "hold": hold,
        "digit_leak": leak,
        "hid_failure_lie": hid_lie,
        "truth_dest": truth,
        "citation": cite,
        "issue_kind": kind if not hold or kind in {"digit_leak", "truth_dest", "empty_hid_success"} else kind,
        "licenses_digits": False,
        "seals": False,
        "reason": (
            "digit_leak"
            if leak
            else "truth_dest"
            if truth
            else "hid_failure_lie"
            if hid_lie
            else "contradicted"
            if cite == "contradicts"
            else "export_ok"
        ),
    }


def local_hygiene_answers(envelope: dict[str, Any]) -> dict[str, Any]:
    leak = unlocked_digit_leak(envelope)
    hid_lie = dualsense_treated_as_failure(envelope)
    truth = truth_dest_named(envelope)
    hid_ok = envelope.get("hid_on_console") is True
    return {
        "digit_leak_noul": 0.9 if leak else 0.08,
        "hid_fail_noul": 0.85 if hid_lie else 0.1,
        "citation": "contradicts" if leak else "supports",
        "citation_confidence": 0.86,
        "issue_kind": (
            "digit_leak"
            if leak
            else "truth_dest"
            if truth
            else "empty_hid_success"
            if hid_ok
            else "no_match"
        ),
        "source": "local_heuristic",
    }


def inspect_envelope(envelope: dict[str, Any], *, ask_fn: Any = None) -> dict[str, Any]:
    # Deterministic hard-holds refuse before any model call.
    if (
        unlocked_digit_leak(envelope)
        or truth_dest_named(envelope)
        or dualsense_treated_as_failure(envelope)
    ):
        out = compose_hygiene(envelope)
        out["source"] = "preflight"
        return out
    answers = None
    if ask_fn is not None:
        answers = ask_fn(envelope)
    if answers is None and _env_jev():
        answers = _try_typesafe(envelope)
    if answers is None:
        answers = local_hygiene_answers(envelope)
    out = compose_hygiene(
        envelope,
        digit_leak_noul=answers.get("digit_leak_noul"),
        hid_fail_noul=answers.get("hid_fail_noul"),
        citation=answers.get("citation"),
        citation_confidence=answers.get("citation_confidence"),
        issue_kind=answers.get("issue_kind"),
    )
    out["source"] = answers.get("source")
    return out


def _try_typesafe(envelope: dict[str, Any]) -> dict[str, Any] | None:
    # Env key first; else load .secrets/typesafe.key without logging it.
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        try:
            from pathlib import Path

            raw = Path(".secrets/typesafe.key").read_text(encoding="utf-8").strip()
            if not raw:
                return None
            os.environ["TYPESAFE_API_KEY"] = raw
        except Exception:
            return None
    questions = hygiene_questions()
    if not questions:
        return None
    try:
        from typesafe_sdk import TypeSafeClient

        with TypeSafeClient() as client:
            response = client.system_one(
                state={
                    "envelope": envelope,
                    "policy": "observation only; never seal; never license unlocked digits",
                },
                questions=questions,
            )
        nouls = getattr(response, "nouls", {}) or {}
        choices = getattr(response, "choices", {}) or {}
        d = nouls.get("digit_leak")
        h = nouls.get("hid_failure_lie")
        c = choices.get("citation")
        k = choices.get("issue_kind")
        return {
            "digit_leak_noul": float(d.noul) if d is not None else None,
            "hid_fail_noul": float(h.noul) if h is not None else None,
            "citation": getattr(c, "choice", None) if c is not None else None,
            "citation_confidence": float(getattr(c, "confidence", 0) or 0)
            if c is not None
            else None,
            "issue_kind": getattr(k, "choice", None) if k is not None else None,
            "source": "typesafe",
        }
    except Exception as e:
        log.debug("recap hygiene typesafe skipped: %s", e)
        return None
