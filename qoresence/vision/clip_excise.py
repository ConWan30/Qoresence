"""Clip excision — Span Referee + Cut Receipt (observation plane, default OFF).

After an HDMI clip is written, candidate dead spans (pause / menu / loading /
frozen picture) are judged *post hoc* from evidence recorded inside each span,
then cut from a separate render. The original MP4 is never modified.

Enable with ``--clip-excise`` or ``QORESENCE_CLIP_EXCISE=1``. ``--play`` does
not turn this on.

HARD RULES (same class as AGENTS.md Rules 5–6):

1. Never emit bus events, never take a lobe lock, never run on the capture thread.
2. Never license score digits; never rank play quality (no highlight / best / clutch).
3. Uncertain spans are kept. No TypeSafe key → only Triple-Proof pauses may be cut.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"
POLICY_VERSION = "excise-v1"
DEFAULT_MODEL = "jev-1.13.0"

MIN_SPAN_S = 1.5
MERGE_GAP_S = 0.5
MAX_SPANS = 12
STILL_HZ = 10.0
STILL_DIFF_MAX = 2.0  # mean |Δ| on 0..255 gray at 64x36
STILL_MIN_S = 1.5
OPTIONS_BEFORE_S = 1.0
OPTIONS_AFTER_S = 0.5
OPTIONS_BUTTONS = frozenset({"options", "start"})

CANDIDATE_KINDS = frozenset({"pause", "select_plate", "menu", "loading"})
TICKET_MARK_PREFIXES = ("confirm", "fast_", "arm", "prediction_")
SPAN_KINDS = ("gameplay", "pause", "menu", "loading", "replay_or_cutscene", "unknown")

_CONF_RANK = {"lo": 0, "mid": 1, "hi": 2}
_PAUSE_RANK = {"no": 0, "na": 1, "maybe": 2, "yes": 3}

_enabled_override: bool | None = None


def set_enabled(on: bool | None) -> None:
    """CLI hook; ``None`` falls back to the environment."""
    global _enabled_override
    _enabled_override = None if on is None else bool(on)


def excise_enabled() -> bool:
    if _enabled_override is not None:
        return _enabled_override
    return os.environ.get("QORESENCE_CLIP_EXCISE", "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }


def excise_model() -> str:
    return os.environ.get("QORESENCE_EXCISE_MODEL", "").strip() or DEFAULT_MODEL


# --------------------------------------------------------------------------- evidence


def stillness_series(
    frames: list[tuple[float, bytes]], *, hz: float = STILL_HZ
) -> list[tuple[float, float]]:
    """``(t_rel_s, mean_abs_diff)`` between sampled frames (64x36 gray).

    ``frames`` are ``(monotonic_ts_s, jpeg)``; ``t_rel_s`` is the later frame's
    offset from the first frame. Undecodable frames are skipped.
    """
    if len(frames) < 2:
        return []
    try:
        import cv2
        import numpy as np
    except Exception:
        return []
    t_first = float(frames[0][0])
    step = 1.0 / max(0.5, float(hz))
    out: list[tuple[float, float]] = []
    prev = None
    next_t = t_first
    for ts, jpeg in frames:
        ts = float(ts)
        if ts < next_t:
            continue
        next_t = ts + step * 0.999
        try:
            arr = np.frombuffer(jpeg, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_REDUCED_GRAYSCALE_8)
            if img is None:
                continue
            small = cv2.resize(img, (64, 36), interpolation=cv2.INTER_AREA).astype(np.int16)
        except Exception:
            continue
        if prev is not None:
            out.append((round(ts - t_first, 3), float(np.abs(small - prev).mean())))
        prev = small
    return out


def still_runs(
    series: list[tuple[float, float]],
    *,
    max_diff: float = STILL_DIFF_MAX,
    min_s: float = STILL_MIN_S,
) -> list[list[float]]:
    """Intervals where every sampled diff stays ≤ ``max_diff`` for ≥ ``min_s``."""
    runs: list[list[float]] = []
    start = None
    last_t = None
    prev_t = 0.0
    for t, diff in series:
        if diff <= max_diff:
            if start is None:
                start = prev_t
            last_t = t
        else:
            if start is not None and last_t is not None and last_t - start >= min_s:
                runs.append([round(start, 3), round(last_t, 3)])
            start = None
            last_t = None
        prev_t = t
    if start is not None and last_t is not None and last_t - start >= min_s:
        runs.append([round(start, 3), round(last_t, 3)])
    return runs


def collect_evidence(
    start_ns: int,
    end_ns: int,
    *,
    stillness: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Gather clip-relative evidence from the observation plane (copies only)."""
    dur = max(0.0, (int(end_ns) - int(start_ns)) / 1e9)

    def rel(cns: Any) -> float:
        return round((int(cns or 0) - int(start_ns)) / 1e9, 3)

    ev: dict[str, Any] = {
        "duration_s": round(dur, 3),
        "segments": [],
        "vlm": [],
        "inputs": [],
        "marks": [],
        "still_runs": still_runs(stillness or []),
    }
    try:
        from qoresence.observability.noul_observatory import get_noul_observatory
        from qoresence.vision.clip_chapters import build_segments_for_window

        obs = get_noul_observatory()
        if obs is not None and getattr(obs, "enabled", False):
            ev["segments"] = build_segments_for_window(
                obs.runs_in_window_detailed(start_ns, end_ns),
                start_ns=start_ns,
                end_ns=end_ns,
            )
            ev["vlm"] = [
                {k: v for k, v in dict(e, t_s=rel(e.get("clock_ns"))).items() if k != "clock_ns"}
                for e in obs.evidence_in_window(start_ns, end_ns)
            ]
    except Exception as e:
        log.debug("excise noul evidence skipped: %s", e)
    try:
        import time

        from qoresence.sync.input_ring import get_input_ring

        lookback = max(dur, (time.monotonic_ns() - int(start_ns)) / 1e9) + 1.0
        for e in get_input_ring().snapshot(seconds=lookback):
            cns = int(e.get("clock_ns") or 0)
            if start_ns - int(OPTIONS_BEFORE_S * 1e9) <= cns <= end_ns and e.get("name"):
                ev["inputs"].append(
                    {"t_s": rel(cns), "name": str(e["name"]).lower(), "kind": e.get("kind")}
                )
    except Exception as e:
        log.debug("excise input evidence skipped: %s", e)
    try:
        from qoresence.agents.session_timeline import get_session_timeline

        for t in get_session_timeline().events_in_window(start_ns, end_ns):
            d = t.to_dict() if hasattr(t, "to_dict") else dict(t)
            ev["marks"].append({"t_s": rel(d.get("clock_ns")), "kind": str(d.get("kind") or "")})
    except Exception as e:
        log.debug("excise timeline evidence skipped: %s", e)
    return ev


# --------------------------------------------------------------------------- spans


@dataclass
class Span:
    id: str
    t0_s: float
    t1_s: float
    kinds: list[str]
    confidence: str = "lo"
    true_pause: str = "na"
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def length_s(self) -> float:
        return round(self.t1_s - self.t0_s, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "t0_s": round(self.t0_s, 3),
            "t1_s": round(self.t1_s, 3),
            "kinds": list(self.kinds),
            "confidence": self.confidence,
            "true_pause": self.true_pause,
            "evidence": self.evidence,
        }


def _weakest(rank: dict[str, int], a: str, b: str) -> str:
    return a if rank.get(a, 0) <= rank.get(b, 0) else b


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _span_evidence(t0: float, t1: float, ev: dict[str, Any]) -> dict[str, Any]:
    vlm = sorted(ev.get("vlm") or [], key=lambda v: float(v.get("t_s") or 0))
    inside = [v for v in vlm if t0 <= float(v.get("t_s") or 0) <= t1]
    before = [v for v in vlm if float(v.get("t_s") or 0) < t0]
    after = [v for v in vlm if float(v.get("t_s") or 0) > t1]

    def slim(v: dict[str, Any] | None) -> dict[str, Any] | None:
        if not v:
            return None
        return {
            k: v.get(k) for k in ("t_s", "clock", "quarter", "has_teams", "paused_raw", "prompt")
        }

    options = [
        i
        for i in ev.get("inputs") or []
        if i.get("name") in OPTIONS_BUTTONS
        and t0 - OPTIONS_BEFORE_S <= float(i.get("t_s") or 0) <= t0 + OPTIONS_AFTER_S
    ]
    presses_inside = sum(
        1
        for i in ev.get("inputs") or []
        if t0 <= float(i.get("t_s") or 0) <= t1 and i.get("kind") in ("press", "trigger", None)
    )
    marks = [
        m.get("kind")
        for m in ev.get("marks") or []
        if t0 <= float(m.get("t_s") or 0) <= t1 and m.get("kind")
    ]
    still_s = sum(_overlap(t0, t1, float(r[0]), float(r[1])) for r in ev.get("still_runs") or [])
    return {
        "vlm_before": slim(before[-1] if before else None),
        "vlm_start": slim(inside[0] if inside else None),
        "vlm_mid": slim(inside[len(inside) // 2] if inside else None),
        "vlm_end": slim(inside[-1] if inside else None),
        "vlm_after": slim(after[0] if after else None),
        "vlm_inside": [slim(v) for v in inside],
        "still_s": round(still_s, 3),
        "options_press_before_s": round(t0 - float(options[-1]["t_s"]), 3) if options else None,
        "presses_inside": presses_inside,
        "chapter_marks_inside": marks,
        "ticket_overlap": any(str(k).startswith(TICKET_MARK_PREFIXES) for k in marks),
    }


def build_candidate_spans(
    ev: dict[str, Any],
    *,
    min_s: float = MIN_SPAN_S,
    max_spans: int = MAX_SPANS,
) -> list[Span]:
    """Candidate dead spans from segments and frozen-picture runs, merged, capped."""
    raw: list[dict[str, Any]] = []
    for s in ev.get("segments") or []:
        if s.get("hud_kind") in CANDIDATE_KINDS:
            raw.append(
                {
                    "t0": float(s.get("t0_s") or 0),
                    "t1": float(s.get("t1_s") or 0),
                    "kinds": {str(s["hud_kind"])},
                    "confidence": str(s.get("confidence") or "lo"),
                    "true_pause": str(s.get("true_pause") or "na"),
                    "from_segment": True,
                }
            )
    for r in ev.get("still_runs") or []:
        raw.append(
            {
                "t0": float(r[0]),
                "t1": float(r[1]),
                "kinds": {"still"},
                "confidence": "lo",
                "true_pause": "na",
                "from_segment": False,
            }
        )
    raw.sort(key=lambda r: (r["t0"], r["t1"]))

    merged: list[dict[str, Any]] = []
    for r in raw:
        if merged and r["t0"] <= merged[-1]["t1"] + MERGE_GAP_S:
            m = merged[-1]
            m["t1"] = max(m["t1"], r["t1"])
            m["kinds"] |= r["kinds"]
            if r["from_segment"]:
                if m["from_segment"]:
                    m["confidence"] = _weakest(_CONF_RANK, m["confidence"], r["confidence"])
                    m["true_pause"] = _weakest(_PAUSE_RANK, m["true_pause"], r["true_pause"])
                else:
                    m["confidence"], m["true_pause"] = r["confidence"], r["true_pause"]
                m["from_segment"] = True
            continue
        merged.append(dict(r, kinds=set(r["kinds"])))

    dur = float(ev.get("duration_s") or 0) or None
    spans: list[Span] = []
    for m in merged:
        t0 = max(0.0, m["t0"])
        t1 = min(dur, m["t1"]) if dur else m["t1"]
        if t1 - t0 < float(min_s):
            continue
        if len(spans) >= int(max_spans):
            break
        spans.append(
            Span(
                id=f"s{len(spans)}",
                t0_s=round(t0, 3),
                t1_s=round(t1, 3),
                kinds=sorted(m["kinds"]),
                confidence=m["confidence"],
                true_pause=m["true_pause"],
                evidence=_span_evidence(t0, t1, ev),
            )
        )
    return spans


# --------------------------------------------------------------------------- offline proof


def clock_frozen(span: Span) -> bool:
    """Football adapter: the scorebug game clock reads the same across the span."""
    clocks = [
        v.get("clock")
        for v in span.evidence.get("vlm_inside") or []
        if v and v.get("clock") not in (None, "")
    ]
    return len(clocks) >= 2 and len(set(clocks)) == 1


def triple_proof(span: Span) -> tuple[bool, list[str]]:
    """Offline pause proof: raw pause read + frozen picture + (clock frozen or Options)."""
    reasons: list[str] = []
    inside = [v for v in span.evidence.get("vlm_inside") or [] if v]
    paused = bool(inside) and all(bool(v.get("paused_raw")) for v in inside)
    if paused:
        reasons.append("paused_raw")
    still = float(span.evidence.get("still_s") or 0) >= STILL_MIN_S
    if still:
        reasons.append("still")
    frozen = clock_frozen(span)
    if frozen:
        reasons.append("clock_frozen")
    options = span.evidence.get("options_press_before_s") is not None
    if options:
        reasons.append("options_press")
    return bool(paused and still and (frozen or options)), reasons


# --------------------------------------------------------------------------- Span Referee


def referee_state(spans: list[Span], *, game_profile: str | None = None) -> dict[str, Any]:
    return {
        "game_profile": game_profile or "unknown",
        "policy": "Observation only. Never judge play quality. Never license score digits.",
        "spans": [
            {
                "id": s.id,
                "t0_s": s.t0_s,
                "t1_s": s.t1_s,
                "length_s": s.length_s,
                "segment_kinds": s.kinds,
                **{
                    k: s.evidence.get(k)
                    for k in (
                        "vlm_before",
                        "vlm_start",
                        "vlm_mid",
                        "vlm_end",
                        "vlm_after",
                        "still_s",
                        "options_press_before_s",
                        "presses_inside",
                        "chapter_marks_inside",
                        "ticket_overlap",
                    )
                },
            }
            for s in spans
        ],
    }


def referee_questions(spans: list[Span]) -> dict[str, Any]:
    """Three questions per span (fan-out). IDs are for code; text names the span."""
    try:
        from typesafe_sdk import Choice, Noul
    except Exception:
        return {}
    qs: dict[str, Any] = {}
    for i, s in enumerate(spans):
        ref = f"`spans[{i}]`"
        qs[f"{s.id}_kind"] = Choice(
            instructions={
                "question": f"What was on screen during {ref} of this console game clip?",
                "focus": (
                    "Use the vision-model reads at start/mid/end, frozen-picture seconds "
                    "(`still_s`), controller presses and the reads just before/after."
                ),
                "never": "Not a judgment of play quality.",
            },
            criteria={
                "gameplay": {"what": "Live play or pre-play with the game running."},
                "pause": {"what": "In-game pause overlay; gameplay suspended."},
                "menu": {"what": "Main menu, lobby, settings or results screen."},
                "loading": {"what": "Loading screen."},
                "replay_or_cutscene": {"what": "Instant replay, cutscene or presentation."},
                "unknown": {"what": "None of the above fits, or the evidence is too thin."},
            },
        )
        qs[f"{s.id}_suspended"] = Noul(
            instructions={
                "question": (
                    f"Was gameplay suspended for the whole of {ref}, and did it resume "
                    "from the same moment afterwards (for example the game clock reads "
                    "the same before and after)?"
                ),
                "true": "Suspended throughout and resumed where it left off.",
                "false": "Play continued, advanced, or the span includes live action.",
            },
        )
        qs[f"{s.id}_hides_play"] = Noul(
            instructions={
                "question": (
                    f"Would removing {ref} from the clip hide any live-play action, such "
                    "as a snap, a play in motion, or a score change?"
                ),
                "true": "Live action happens inside the span.",
                "false": "Nothing live happens inside the span.",
                "never": "Menu navigation presses during a pause are not live play.",
            },
        )
    return qs


def parse_referee_response(response: Any, spans: list[Span]) -> dict[str, dict[str, Any]]:
    """``{span_id: {kind, kind_confidence, suspended, hides_play}}`` from a response."""
    choices = getattr(response, "choices", None) or {}
    nouls = getattr(response, "nouls", None) or {}
    out: dict[str, dict[str, Any]] = {}
    for s in spans:
        k = choices.get(f"{s.id}_kind")
        sus = nouls.get(f"{s.id}_suspended")
        hp = nouls.get(f"{s.id}_hides_play")
        kind = getattr(k, "choice", None) if k is not None else None
        out[s.id] = {
            "kind": kind if kind in SPAN_KINDS else None,
            "kind_confidence": float(getattr(k, "confidence", 0) or 0) if k is not None else None,
            "suspended": float(sus.noul) if sus is not None else None,
            "hides_play": float(hp.noul) if hp is not None else None,
        }
    return out


def run_referee(
    spans: list[Span],
    *,
    ask_fn: Any = None,
    game_profile: str | None = None,
    model: str | None = None,
    timeout_s: float = 10.0,
) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    """One Jev request for all spans. ``(answers, model_id)`` or ``(None, None)``.

    ``ask_fn(state, spans) -> (answers, model_id)`` replaces the SDK in tests.
    """
    if not spans:
        return {}, None
    state = referee_state(spans, game_profile=game_profile)
    if ask_fn is not None:
        try:
            return ask_fn(state, spans)
        except Exception as e:
            log.debug("excise referee ask_fn failed: %s", e)
            return None, None
    questions = referee_questions(spans)
    if not questions:
        return None, None
    try:
        from qoresence.observability.typesafe_ask import system_one

        response = system_one(
            state=state,
            questions=questions,
            model=model or excise_model(),
            timeout_s=timeout_s,
            warn_label="excise",
            logger=log,
        )
    except Exception as e:
        log.debug("excise referee failed: %s", e)
        return None, None
    if response is None:
        return None, None
    model_id = getattr(response, "model", None) or model or excise_model()
    return parse_referee_response(response, spans), str(model_id)


# --------------------------------------------------------------------------- cut policy

PAD_S = 0.4
MAX_CUT_FRACTION = 0.6
HIDES_PLAY_KEEP = 0.3
KIND_FLOOR = 0.6
KIND_CUT = 0.85
SUSPENDED_CUT = 0.8
NOUL_UNSURE = 0.5
RECEIPT_SCHEMA = "qoresence.cut_receipt/1"
DECISIONS = ("cut", "suggest", "keep")


def cut_policy(span: Span, answers: dict[str, dict[str, Any]] | None) -> tuple[str, str]:
    """``(decision, reason)``; ``answers is None`` means no referee (offline)."""
    ev = span.evidence
    if ev.get("ticket_overlap"):
        return "keep", "ticket_or_mark_inside"
    if span.length_s < MIN_SPAN_S:
        return "keep", "too_short"
    if answers is None:
        ok, reasons = triple_proof(span)
        if ok:
            return "cut", "triple_proof:" + "+".join(reasons)
        return "keep", "offline_no_proof"
    a = answers.get(span.id)
    if not a:
        return "keep", "no_answer"
    hides = a.get("hides_play")
    if hides is None:
        return "keep", "hides_play_unknown"
    if hides >= HIDES_PLAY_KEEP:
        return "keep", "may_hide_play"
    kind = a.get("kind")
    conf = float(a.get("kind_confidence") or 0.0)
    if kind in (None, "unknown", "gameplay"):
        return "keep", f"kind_{kind or 'none'}"
    if conf < KIND_FLOOR:
        return "keep", "kind_unsure"
    if kind == "replay_or_cutscene":
        return "suggest", "replay_is_taste"
    if kind == "pause":
        sus = a.get("suspended")
        if sus is None or sus < NOUL_UNSURE:
            return "keep", "not_suspended"
        if conf >= KIND_CUT and sus >= SUSPENDED_CUT:
            return "cut", "referee_pause"
        return "suggest", "referee_pause_unsure"
    if kind in ("menu", "loading"):
        if conf >= KIND_CUT:
            return "cut", f"referee_{kind}"
        return "suggest", f"referee_{kind}_unsure"
    return "keep", "unhandled_kind"


def effective_decision(span_row: dict[str, Any]) -> str:
    """User override wins; ``suggest`` renders as keep until accepted."""
    user = span_row.get("user")
    if user in ("cut", "keep"):
        return user
    return "cut" if span_row.get("decision") == "cut" else "keep"


def plan_cuts(
    span_rows: list[dict[str, Any]], duration_s: float
) -> tuple[list[list[float]], list[list[float]], bool]:
    """``(cuts, keep, aborted)`` with ``PAD_S`` kept at both edges of every cut."""
    dur = max(0.0, float(duration_s))
    cuts: list[list[float]] = []
    for row in sorted(span_rows, key=lambda r: float(r.get("t0_s") or 0)):
        if effective_decision(row) != "cut":
            continue
        t0 = max(0.0, float(row["t0_s"]) + PAD_S)
        t1 = min(dur, float(row["t1_s"]) - PAD_S)
        if t1 - t0 < MIN_SPAN_S - 2 * PAD_S:
            continue
        if cuts and t0 <= cuts[-1][1]:
            cuts[-1][1] = max(cuts[-1][1], t1)
        else:
            cuts.append([round(t0, 3), round(t1, 3)])
    removed = sum(c[1] - c[0] for c in cuts)
    if dur <= 0 or removed > MAX_CUT_FRACTION * dur:
        return [], [[0.0, round(dur, 3)]], bool(cuts)
    keep: list[list[float]] = []
    cursor = 0.0
    for c0, c1 in cuts:
        if c0 > cursor:
            keep.append([round(cursor, 3), round(c0, 3)])
        cursor = c1
    if cursor < dur:
        keep.append([round(cursor, 3), round(dur, 3)])
    return cuts, keep, False


def time_map(keep: list[list[float]]) -> list[list[float]]:
    """``[edited_t0, source_t0, length]`` rows for each kept range."""
    out = []
    edited = 0.0
    for k0, k1 in keep:
        length = round(k1 - k0, 3)
        out.append([round(edited, 3), round(k0, 3), length])
        edited += length
    return out


def source_time(tmap: list[list[float]], edited_t: float) -> float:
    for e0, s0, length in tmap:
        if e0 <= edited_t <= e0 + length:
            return round(s0 + (edited_t - e0), 3)
    return round(float(edited_t), 3)


def build_receipt(
    source_name: str,
    duration_s: float,
    spans: list[Span],
    answers: dict[str, dict[str, Any]] | None,
    *,
    model_id: str | None,
) -> dict[str, Any]:
    rows = []
    for s in spans:
        decision, reason = cut_policy(s, answers)
        row = s.to_dict()
        row.update(
            {
                "decision": decision,
                "reason": reason,
                "answers": (answers or {}).get(s.id) if answers is not None else None,
                "user": None,
            }
        )
        rows.append(row)
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "plane": PLANE,
        "policy_version": POLICY_VERSION,
        "referee": "none"
        if not spans
        else ("jev" if answers is not None else "offline_triple_proof"),
        "model": model_id if answers is not None else None,
        "source": source_name,
        "source_duration_s": round(float(duration_s), 3),
        "spans": rows,
        "render": {"state": "pending", "path": None},
        "licenses_digits": False,
    }
    return refresh_receipt(receipt)


def refresh_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Recompute cuts / keep / time map from span decisions and user overrides."""
    cuts, keep, aborted = plan_cuts(receipt.get("spans") or [], receipt["source_duration_s"])
    receipt["cuts"] = cuts
    receipt["keep"] = keep
    receipt["time_map"] = time_map(keep)
    receipt["edited_duration_s"] = round(sum(k[1] - k[0] for k in keep), 3)
    if aborted:
        receipt["excision"] = "aborted_too_much"
    elif cuts:
        receipt["excision"] = "applied"
    elif any(r.get("decision") == "suggest" and not r.get("user") for r in receipt["spans"]):
        receipt["excision"] = "suggestions_only"
    else:
        receipt["excision"] = "none"
    return receipt


def apply_user_decision(receipt: dict[str, Any], span_id: str, decision: str) -> bool:
    """Gamer override for one span (``cut`` / ``keep``). Returns False if unknown."""
    if decision not in ("cut", "keep"):
        return False
    for row in receipt.get("spans") or []:
        if row.get("id") == span_id:
            row["user"] = decision
            refresh_receipt(receipt)
            return True
    return False


def is_cut_render(path: Any) -> bool:
    """``<stem>.cut.mp4`` renders are derived views, not clips of their own."""
    return Path(path).name.lower().endswith(".cut.mp4")


def receipt_path(mp4_path: Any) -> Path:
    p = Path(mp4_path)
    return p.with_name(p.stem + ".cut.json")


def cut_mp4_path(mp4_path: Any) -> Path:
    p = Path(mp4_path)
    return p.with_name(p.stem + ".cut.mp4")


def write_receipt(mp4_path: Any, receipt: dict[str, Any]) -> Path:
    out = receipt_path(mp4_path)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    tmp.replace(out)
    return out


def read_receipt(mp4_path: Any) -> dict[str, Any] | None:
    p = receipt_path(mp4_path)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def plan_excision(
    mp4_path: Any,
    *,
    start_ns: int,
    end_ns: int,
    duration_s: float,
    stillness: list[tuple[float, float]] | None = None,
    evidence: dict[str, Any] | None = None,
    ask_fn: Any = None,
    use_referee: bool | None = None,
    game_profile: str | None = None,
) -> dict[str, Any]:
    """Evidence → spans → referee/offline → receipt (written next to the MP4)."""
    ev = (
        evidence
        if evidence is not None
        else collect_evidence(start_ns, end_ns, stillness=stillness)
    )
    ev["duration_s"] = round(float(duration_s), 3)
    spans = build_candidate_spans(ev)
    answers = None
    model_id = None
    if spans and (use_referee if use_referee is not None else _referee_available()):
        answers, model_id = run_referee(spans, ask_fn=ask_fn, game_profile=game_profile)
    receipt = build_receipt(Path(mp4_path).name, duration_s, spans, answers, model_id=model_id)
    if not receipt["cuts"]:
        receipt["render"] = {"state": "not_needed", "path": None}
    write_receipt(mp4_path, receipt)
    _ledger(receipt)
    return receipt


def _referee_available() -> bool:
    """Jev referee only when an observation pack is on (``--noul`` / ``--jev``)."""
    try:
        from qoresence.observability.noul_observatory import get_noul_observatory

        obs = get_noul_observatory()
        if obs is not None and getattr(obs, "enabled", False):
            return True
    except Exception:
        pass
    try:
        from qoresence.observability.jev_conductor import get_jev_conductor

        jev = get_jev_conductor()
        if jev is not None and getattr(jev, "enabled", False):
            return True
    except Exception:
        pass
    return os.environ.get("QORESENCE_JEV", "").strip().lower() in {"1", "true", "on", "yes"}


def _ledger(receipt: dict[str, Any]) -> None:
    try:
        from qoresence.observability.jev_ledger import append_judgment

        append_judgment(
            "excise",
            {
                "source": receipt.get("source"),
                "referee": receipt.get("referee"),
                "model": receipt.get("model"),
                "policy_version": receipt.get("policy_version"),
                "excision": receipt.get("excision"),
                "decisions": [
                    {"id": r["id"], "decision": r["decision"], "reason": r["reason"]}
                    for r in receipt.get("spans") or []
                ],
                "licenses_digits": False,
            },
        )
    except Exception:
        pass


# --------------------------------------------------------------------------- worker + render

WORKER_QUEUE_MAX = 4


def render_from_receipt(mp4_path: Any, receipt: dict[str, Any]) -> dict[str, Any]:
    """Render (or remove) ``<stem>.cut.mp4`` to match the receipt; returns the receipt."""
    src = Path(mp4_path)
    cut = cut_mp4_path(src)
    if not receipt.get("cuts"):
        cut.unlink(missing_ok=True)
        receipt["render"] = {"state": "not_needed", "path": None}
        return receipt
    from qoresence.vision.clip_buffer import HdmiClipBuffer

    res = HdmiClipBuffer.render_cut(src, receipt.get("keep") or [], cut)
    if res.get("ok"):
        receipt["render"] = {"state": "done", "path": cut.name, "audio": res.get("audio")}
    else:
        receipt["render"] = {"state": "failed", "path": None}
    return receipt


class _ExciseWorker:
    """Bounded single worker: referee + render off the export and capture threads."""

    def __init__(self) -> None:
        import queue
        import threading

        self._q: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(maxsize=WORKER_QUEUE_MAX)
        self._thread = threading.Thread(target=self._loop, name="clip-excise", daemon=True)
        self._thread.start()

    def submit(self, kind: str, job: dict[str, Any]) -> bool:
        import queue

        try:
            self._q.put_nowait((kind, job))
            return True
        except queue.Full:
            return False

    def drain(self, timeout_s: float = 30.0) -> bool:
        """Test helper: wait until queued jobs finish."""
        import time

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._q.unfinished_tasks == 0:
                return True
            time.sleep(0.02)
        return False

    def _loop(self) -> None:
        while True:
            kind, job = self._q.get()
            try:
                if kind == "plan":
                    receipt = plan_excision(
                        job["mp4"],
                        start_ns=job["start_ns"],
                        end_ns=job["end_ns"],
                        duration_s=job["duration_s"],
                        evidence=job["evidence"],
                    )
                    if receipt.get("cuts"):
                        write_receipt(job["mp4"], render_from_receipt(job["mp4"], receipt))
                elif kind == "render":
                    receipt = read_receipt(job["mp4"])
                    if receipt is not None:
                        write_receipt(job["mp4"], render_from_receipt(job["mp4"], receipt))
            except Exception as e:
                log.debug("clip excise job failed: %s", e)
            finally:
                self._q.task_done()


_worker: _ExciseWorker | None = None


def get_excise_worker() -> _ExciseWorker:
    global _worker
    if _worker is None:
        _worker = _ExciseWorker()
    return _worker


def submit_excision(mp4_path: Any, *, snapshot: list[Any], duration_s: float) -> bool:
    """Called from ``HdmiClipBuffer.export`` (off the capture thread).

    Stillness and evidence are captured now, before the rings roll; the referee
    and render run on the worker. A full queue writes a ``skipped_busy`` receipt.
    """
    frames = [(float(e[0]), e[1]) for e in snapshot if len(e) >= 2]
    if len(frames) < 2:
        return False
    start_ns = int(frames[0][0] * 1e9)
    end_ns = int(frames[-1][0] * 1e9)
    evidence = collect_evidence(start_ns, end_ns, stillness=stillness_series(frames))
    job = {
        "mp4": str(mp4_path),
        "start_ns": start_ns,
        "end_ns": end_ns,
        "duration_s": float(duration_s),
        "evidence": evidence,
    }
    if get_excise_worker().submit("plan", job):
        return True
    write_receipt(
        mp4_path,
        {
            "schema": RECEIPT_SCHEMA,
            "plane": PLANE,
            "policy_version": POLICY_VERSION,
            "source": Path(mp4_path).name,
            "source_duration_s": round(float(duration_s), 3),
            "spans": [],
            "cuts": [],
            "keep": [[0.0, round(float(duration_s), 3)]],
            "time_map": [[0.0, 0.0, round(float(duration_s), 3)]],
            "edited_duration_s": round(float(duration_s), 3),
            "excision": "skipped_busy",
            "render": {"state": "not_needed", "path": None},
            "licenses_digits": False,
        },
    )
    return False


def request_user_decision(mp4_path: Any, span_id: str, decision: str) -> dict[str, Any] | None:
    """Apply a gamer override and queue a re-render. ``None`` if not applicable."""
    receipt = read_receipt(mp4_path)
    if receipt is None or not apply_user_decision(receipt, span_id, decision):
        return None
    receipt["render"] = {"state": "pending" if receipt["cuts"] else "not_needed", "path": None}
    write_receipt(mp4_path, receipt)
    if not get_excise_worker().submit("render", {"mp4": str(mp4_path)}):
        receipt["render"] = {"state": "skipped_busy", "path": None}
        write_receipt(mp4_path, receipt)
    return receipt


def cut_summary(mp4_path: Any) -> dict[str, Any] | None:
    """Compact cut state for clip listings; ``None`` when no receipt exists."""
    receipt = read_receipt(mp4_path)
    if receipt is None:
        return None
    render = receipt.get("render") or {}
    cut = cut_mp4_path(mp4_path)
    url = f"/media/clips/{cut.name}" if render.get("state") == "done" and cut.is_file() else None
    return {
        "excision": receipt.get("excision"),
        "render": render.get("state"),
        "url": url,
        "receipt_url": f"/media/clips/{receipt_path(mp4_path).name}",
        "source_duration_s": receipt.get("source_duration_s"),
        "edited_duration_s": receipt.get("edited_duration_s"),
        "suggestions": sum(
            1
            for r in receipt.get("spans") or []
            if r.get("decision") == "suggest" and not r.get("user")
        ),
    }
