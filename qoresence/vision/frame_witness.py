"""Frame witness — the JPEG names the situation.

Optical plate tokens decide play, pause, menu, or loading. A locked
scorebug behind Resume is still pause. Silence and conflict abstain.
Noul may answer only when optical abstained, ``--noul`` is already on,
and no witness call is in flight. The model never licenses digits.

The capture thread does not run this module. A daemon copies the latest
JPEG about once a second. Freshness is about one second of age. Same-seq
slack stays on widget ghosts; using it here would flicker a 1 Hz plate.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

KINDS = frozenset({"play", "pause", "menu", "loading", "abstain"})
NOT_PLAY = frozenset({"pause", "menu", "loading"})
SOURCES = frozenset({"optical", "noul", "none"})
# A 1 Hz plate must still be fresh on the next sample.
WITNESS_MAX_AGE_S = 1.25
# Clip rings are monotonic seconds. A missed tick wider than this breaks a span.
WITNESS_SPAN_GAP_S = 1.6
_TAPE_MAX = 240

_PAUSE_TOKENS = ("RESUME", "PAUSED", "INSTANT REPLAY", "RETURN TO HUB")
_MENU_TOKENS = ("PRESS ANY BUTTON", "QUICK PLAY", "PLAY NOW")
_PLAY_TOKENS = ("PLAY CALL", "AUDIBLE")
_CLOCK_RE_TEXT = re.compile(r"\b\d{1,2}:\d{2}\b")

_lock = threading.Lock()
_noul_gate = threading.Lock()
_start_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None
_noul_on = False
_ask_for_tests: Callable[[dict[str, Any]], str | None] | None = None
_ocr_ready: bool | None = None


@dataclass(frozen=True)
class FrameEvidence:
    """Cues already on the vision path. Empty text abstains."""

    profile: str | None = None
    plate_text: str = ""
    paused_raw: bool | None = None
    scorebug: bool | None = None


@dataclass
class _Record:
    kind: str = "abstain"
    source: str = "none"
    mono: float = 0.0
    frame_seq: int = 0
    clock_ns: int = 0


_record = _Record()
_tape: list[dict[str, Any]] = []


def profile_ok(profile: str | None) -> bool:
    p = str(profile or "").lower()
    if not p:
        return False
    return any(k in p for k in ("madden", "ncaa", "cfb", "football"))


def witness_kind(evidence: FrameEvidence) -> str:
    """Closed-set kind. Conflict and silence are abstain. Never loading on a kickoff clock."""

    if not profile_ok(evidence.profile):
        return "abstain"
    text = " ".join(str(evidence.plate_text or "").upper().split())
    pause = any(tok in text for tok in _PAUSE_TOKENS)
    menu = any(tok in text for tok in _MENU_TOKENS)
    loading = "YOUR PROGRESS" in text or ("QUICK MATCH" in text and "ADVANCE" in text)
    play_call = any(tok in text for tok in _PLAY_TOKENS)
    clock = _CLOCK_RE_TEXT.search(text) is not None
    kickoff = "KICKOFF" in text or "KICK OFF" in text

    named = [name for name, hit in (("pause", pause), ("menu", menu), ("loading", loading)) if hit]
    if len(named) > 1:
        return "abstain"
    if named:
        return named[0]
    if evidence.paused_raw is True and (play_call or kickoff):
        return "abstain"
    if evidence.paused_raw is True:
        return "pause"
    if play_call or (kickoff and clock) or (bool(evidence.scorebug) and clock):
        return "play"
    return "abstain"


def resolve_witness(
    evidence: FrameEvidence,
    *,
    noul: bool = False,
    ask: Callable[[dict[str, Any]], str | None] | None = None,
) -> tuple[str, str]:
    """Optical first. Noul only on abstain. A missed ask stores abstain / none."""

    kind = witness_kind(evidence)
    if kind != "abstain":
        return kind, "optical"
    if not noul or not profile_ok(evidence.profile) or ask is None:
        return "abstain", "none"
    if not _noul_gate.acquire(blocking=False):
        return "abstain", "busy"
    try:
        try:
            choice = ask(_evidence_state(evidence))
        except Exception as e:
            log.debug("frame witness noul skipped: %s", e)
            choice = None
    finally:
        _noul_gate.release()
    picked = str(choice or "").strip().lower()
    if picked in {"play", "pause", "menu", "loading"}:
        return picked, "noul"
    return "abstain", "none"


def _evidence_state(evidence: FrameEvidence) -> dict[str, Any]:
    return {
        "profile": evidence.profile or "",
        "plate_text": evidence.plate_text or "",
        "paused_raw": evidence.paused_raw,
        "scorebug": bool(evidence.scorebug),
        "policy": "observation only; never license score digits",
    }


def publish_witness(
    kind: str,
    source: str,
    *,
    frame_seq: int = 0,
    clock_ns: int = 0,
    mono: float | None = None,
) -> None:
    """Store one reading. Does not emit and does not take a lobe lock."""

    k = kind if kind in KINDS else "abstain"
    src = source if source in SOURCES else "none"
    if k == "abstain":
        src = "none"
    rec = _Record(
        kind=k,
        source=src,
        mono=time.monotonic() if mono is None else float(mono),
        frame_seq=int(frame_seq or 0),
        clock_ns=int(clock_ns or 0),
    )
    global _record
    with _lock:
        _record = rec
        _tape.append(
            {
                "mono": rec.mono,
                "kind": rec.kind,
                "source": rec.source,
                "frame_seq": rec.frame_seq,
                "clock_ns": rec.clock_ns,
            }
        )
        if len(_tape) > _TAPE_MAX:
            del _tape[: len(_tape) - _TAPE_MAX]


def public_witness(now: float | None = None) -> dict[str, Any]:
    """Applied reading. Stale or abstain is fresh=false and does not rename the frame."""

    with _lock:
        rec = _record
    if rec.mono <= 0 or rec.source == "none" or rec.kind not in {"play", "pause", "menu", "loading"}:
        return {
            "kind": "abstain",
            "source": "none",
            "age_s": None,
            "fresh": False,
            "frame_seq": rec.frame_seq,
            "clock_ns": rec.clock_ns,
        }
    age = max(0.0, (time.monotonic() if now is None else float(now)) - rec.mono)
    fresh = age <= WITNESS_MAX_AGE_S
    if not fresh:
        return {
            "kind": "abstain",
            "source": "none",
            "age_s": round(age, 3),
            "fresh": False,
            "frame_seq": rec.frame_seq,
            "clock_ns": rec.clock_ns,
        }
    return {
        "kind": rec.kind,
        "source": rec.source,
        "age_s": round(age, 3),
        "fresh": True,
        "frame_seq": rec.frame_seq,
        "clock_ns": rec.clock_ns,
    }


def applied_kind() -> str | None:
    """Fresh play/pause/menu/loading, else None so paint keeps today's rules."""

    w = public_witness()
    if not w.get("fresh"):
        return None
    kind = str(w.get("kind") or "")
    return kind if kind in {"play", "pause", "menu", "loading"} else None


def witness_blocks_heat() -> bool:
    kind = applied_kind()
    return kind in NOT_PLAY


def heat_state_for(effective: str | None) -> str:
    """Phrase / heat note. Not-play witness wins. Loading notes as paused."""

    kind = applied_kind()
    if kind == "loading":
        return "paused"
    if kind in {"pause", "menu"}:
        return kind
    return str(effective or "")


def reset_witness_for_tests() -> None:
    global _record, _ask_for_tests, _noul_on, _ocr_ready
    with _lock:
        _record = _Record()
        _tape.clear()
    _ask_for_tests = None
    _noul_on = False
    _ocr_ready = None


def samples_in_window(start_ns: int, end_ns: int) -> list[dict[str, Any]]:
    """Witness samples inside a clip ring.

    ``start_ns`` / ``end_ns`` are monotonic seconds times 1e9, the same clock
    ``HdmiClipBuffer`` stores on each frame. ``frame_seq`` is recorded for the
    tape. It does not place the sample.
    """

    start = int(start_ns) / 1e9
    end = int(end_ns) / 1e9
    if end < start:
        return []
    with _lock:
        rows = list(_tape)
    out: list[dict[str, Any]] = []
    for row in rows:
        mono = float(row.get("mono") or 0)
        if mono < start or mono > end:
            continue
        out.append(
            {
                "t_s": round(mono - start, 3),
                "kind": row.get("kind"),
                "source": row.get("source"),
                "frame_seq": int(row.get("frame_seq") or 0),
            }
        )
    return out


def collapse_witness_spans(
    samples: list[dict[str, Any]],
    *,
    min_s: float = 1.5,
    max_gap_s: float = WITNESS_SPAN_GAP_S,
) -> list[dict[str, Any]]:
    """Consecutive fresh pause/menu/loading samples become spans.

    ``play`` and ``abstain`` break a run. A run shorter than ``min_s`` is dropped.
    The span ends at the breaking sample when that sample is close, so the
    proposal covers the dead stretch and stops where the frame changes.
    """

    dead = {"pause", "menu", "loading"}
    ordered = sorted(
        (
            s
            for s in samples
            if isinstance(s, dict) and str(s.get("kind") or "") in dead | {"play", "abstain"}
        ),
        key=lambda s: float(s.get("t_s") or 0),
    )
    out: list[dict[str, Any]] = []
    i = 0
    n = len(ordered)
    while i < n:
        kind = str(ordered[i].get("kind") or "")
        if kind not in dead:
            i += 1
            continue
        start = float(ordered[i].get("t_s") or 0)
        last = start
        source = str(ordered[i].get("source") or "none")
        j = i + 1
        while j < n:
            t = float(ordered[j].get("t_s") or 0)
            if t - last > max_gap_s or str(ordered[j].get("kind") or "") != kind:
                break
            last = t
            j += 1
        if j < n and float(ordered[j].get("t_s") or 0) - last <= max_gap_s:
            end = float(ordered[j].get("t_s") or 0)
        else:
            end = last
        if end - start >= float(min_s):
            out.append(
                {
                    "t0_s": round(start, 3),
                    "t1_s": round(end, 3),
                    "kind": kind,
                    "source": source,
                }
            )
        i = j if j > i else i + 1
    return out


def set_noul_ask_for_tests(ask: Callable[[dict[str, Any]], str | None] | None) -> None:
    global _ask_for_tests
    _ask_for_tests = ask


def _noul_enabled() -> bool:
    if _noul_on:
        return True
    return os.environ.get("QORESENCE_NOUL", "").strip().lower() in {"1", "true", "on", "yes"}


def _default_ask(state: dict[str, Any]) -> str | None:
    if _ask_for_tests is not None:
        return _ask_for_tests(state)
    try:
        from qoresence.observability.typesafe_ask import key_present, system_one
    except Exception:
        return None
    if not key_present():
        return None
    try:
        from typesafe_sdk import Choice
    except Exception:
        return None
    questions = {
        "frame_kind": Choice(
            instructions={
                "question": (
                    "Which situation is this plate? A scorebug behind Resume is "
                    "still pause. A play-call, Subs, or audible HUD is play. "
                    "A kickoff with a game clock is play, not loading."
                ),
                "focus": "Name the plate. Code owns digit licensing.",
                "never": "Do not invent a score. Abstain when the plate is silent or mixed.",
            },
            criteria={
                "play": {"what": "Live snap or preplay stick with a clock or play-call HUD."},
                "pause": {"what": "In-game pause overlay, including Resume over a visible scorebug."},
                "menu": {"what": "Front end: Press Any Button, Quick Play, Play Now, settings, results."},
                "loading": {"what": "Progress plate such as YOUR PROGRESS / QUICK MATCH, or a dark transition."},
                "abstain": {"what": "Cues disagree or the plate does not say."},
            },
        )
    }
    response = system_one(
        state=state,
        questions=questions,
        timeout_s=4.0,
        warn_label="frame-witness",
        logger=log,
    )
    if response is None:
        return None
    choices = getattr(response, "choices", {}) or {}
    picked = choices.get("frame_kind")
    return getattr(picked, "choice", None) if picked is not None else None


def _situation() -> dict[str, Any]:
    try:
        from qoresence.deck.server import _state

        sit = _state.situation
        return sit if isinstance(sit, dict) else {}
    except Exception:
        return {}


def _vlm_last() -> dict[str, Any]:
    try:
        from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

        last = get_scoreboard_vlm().get_last()
        return last if isinstance(last, dict) else {}
    except Exception:
        return {}


def _ocr_plate_text() -> str:
    """Tesseract on a copied JPEG, off the capture thread. Missing engine abstains."""

    global _ocr_ready
    if _ocr_ready is False:
        return ""
    try:
        from qoresence.vision.clip_buffer import get_latest_jpeg

        jpg = get_latest_jpeg() or b""
    except Exception:
        return ""
    if not jpg:
        return ""
    try:
        import cv2
        import numpy as np

        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return ""
    if frame is None:
        return ""
    try:
        from qoresence.vision.scoreboard_ocr_engine import TesseractScoreboardEngine

        eng = TesseractScoreboardEngine()
        if not eng.is_ready():
            _ocr_ready = False
            return ""
        _ocr_ready = True
        h, w = frame.shape[:2]
        if w > 640:
            frame = cv2.resize(frame, (640, max(1, int(round(h * 640 / w)))), interpolation=cv2.INTER_AREA)
        boxes = eng.read_boxes(frame)
        return " ".join(str(getattr(b, "text", "") or "") for b in boxes)
    except Exception:
        _ocr_ready = False
        return ""


def collect_evidence() -> FrameEvidence:
    sit = _situation()
    last = _vlm_last()
    vc = last.get("visible_control") if isinstance(last.get("visible_control"), dict) else {}
    parts = [str(vc.get("prompt") or ""), _ocr_plate_text()]
    paused = last.get("paused_raw")
    if paused is None:
        paused = last.get("paused")
    paused_raw = paused if isinstance(paused, bool) else None
    scorebug = bool(
        last.get("left_team")
        or last.get("home_team")
        or (last.get("home_score") is not None and last.get("away_score") is not None)
        or (last.get("left_score") is not None and last.get("right_score") is not None)
    )
    profile = sit.get("game_profile") or last.get("game_profile")
    return FrameEvidence(
        profile=str(profile) if profile else None,
        plate_text=" ".join(p for p in parts if p),
        paused_raw=paused_raw,
        scorebug=scorebug,
    )


def _stamp() -> tuple[int, int]:
    try:
        from qoresence.monitor.frame_hub import get_frame_hub

        st = get_frame_hub().get_latest_stamp() or {}
        return int(st.get("seq") or 0), int(st.get("clock_ns") or 0)
    except Exception:
        return 0, 0


def witness_tick(evidence: FrameEvidence | None = None, *, noul: bool | None = None) -> dict[str, Any]:
    """One sample. Busy Noul does not wipe the slot."""

    ev = evidence if evidence is not None else collect_evidence()
    use_noul = _noul_enabled() if noul is None else bool(noul)
    kind, source = resolve_witness(ev, noul=use_noul, ask=_default_ask if use_noul else None)
    if source == "busy":
        return public_witness()
    seq, clock = _stamp()
    publish_witness(kind, source, frame_seq=seq, clock_ns=clock)
    return public_witness()


def _loop() -> None:
    while not _stop.is_set():
        try:
            witness_tick()
        except Exception as e:
            log.debug("frame witness tick skipped: %s", e)
        _stop.wait(1.0)


def start_witness_worker(*, noul: bool = False) -> None:
    """Daemon sampler. Idempotent. Does not open the capture card."""

    global _noul_on, _thread
    if noul:
        _noul_on = True
    with _start_lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="frame-witness", daemon=True)
        _thread.start()


def stop_witness_worker() -> None:
    _stop.set()
