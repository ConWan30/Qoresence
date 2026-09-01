"""Optical title-presence — observation record + hysteresis FSM.

Wraps GameAutoDetector. Default-OFF. Observation plane only.
No scores, names, eligibility, or truth-plane writes.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

PLANE = "qoresence-observation"
SOURCE_LOBE = "fusion"

HYST_UNKNOWN = "unknown"
HYST_TRANSITIONING = "transitioning"
HYST_OVERLAY = "overlay-rejected"
HYST_LOCKED = "locked"
HYST_STATES = (HYST_UNKNOWN, HYST_TRANSITIONING, HYST_OVERLAY, HYST_LOCKED)

OVERLAY_STATES = frozenset({"menu", "lobby", "hub", "paused"})
GAMEPLAY_STATES = frozenset({"gameplay", "playing", "in_game", "replay", "spectating"})

FOOTBALL_PROFILES = frozenset(
    {"ncaa_football_27", "ncaa_cfb_26", "ncaa_cfb_27", "cfb_27", "madden_27", "madden"}
)
SHOOTER_PROFILES = frozenset({"call_of_duty", "cod"})

NO_CLAIM_REASONS = frozenset(
    {
        "below_threshold",
        "not_locked",
        "overlay_rejected",
        "no_frame",
        "feature_off",
        "plane_invalid",
        "no_result",
    }
)


def title_family_for(profile_id: str | None) -> str | None:
    if not profile_id:
        return None
    key = str(profile_id).lower()
    if any(k in key for k in FOOTBALL_PROFILES) or "ncaa" in key or "madden" in key:
        return "football"
    if any(k in key for k in SHOOTER_PROFILES) or "duty" in key:
        return "shooter"
    return "unknown"


def is_overlay_state(
    game_state: str | None,
    *,
    locked_board: bool = False,
    quarter: int | None = None,
    down: int | None = None,
) -> bool:
    raw = str(game_state or "").lower()
    if not raw or raw in GAMEPLAY_STATES or raw == "unknown":
        return False
    if raw not in OVERLAY_STATES:
        return False
    try:
        from qoresence.profiles.cfb27_product import effective_game_state

        eff = str(
            effective_game_state(raw, locked=locked_board, quarter=quarter, down=down) or raw
        ).lower()
        return eff in OVERLAY_STATES
    except Exception:
        return True


def step_hysteresis(
    *,
    has_frame: bool,
    confidence: float,
    threshold: float,
    consecutive: int,
    stability_count: int,
    overlay: bool,
    profile_changed: bool,
) -> tuple[str, str | None]:
    """Return (hysteresis_state, no_claim_reason|None).

    ``consecutive`` is the incumbent streak *after* this tick's increment/reset,
    except overlay does not increment toward lock (caller must not increment).
    """
    if not has_frame:
        return HYST_UNKNOWN, "no_frame"
    if overlay:
        return HYST_OVERLAY, "overlay_rejected"
    if confidence < float(threshold):
        return HYST_UNKNOWN, "below_threshold"
    need = max(1, int(stability_count))
    if consecutive >= need and not profile_changed:
        return HYST_LOCKED, None
    return HYST_TRANSITIONING, "not_locked"


def no_claim_record(
    *,
    session_id: str,
    clock_ns: int,
    session_head_ns: int | None,
    reason: str,
    hysteresis_state: str = HYST_UNKNOWN,
    confidence: float = 0.0,
    threshold: float = 0.65,
    consecutive: int = 0,
    stability_count: int = 2,
    evidence_count: int = 0,
    vlm_confidence: float = 0.0,
    ocr_confidence: float = 0.0,
    motion_confidence: float = 0.0,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    why = reason if reason in NO_CLAIM_REASONS else "not_locked"
    try:
        from qoresence.graphs.negative_evidence import record_absence

        record_absence(why, session_id=session_id, clock_ns=int(clock_ns))
    except Exception:
        pass
    return {
        "plane": PLANE,
        "session_id": session_id,
        "clock_ns": int(clock_ns),
        "session_head_ns": session_head_ns,
        "source_lobe": SOURCE_LOBE,
        "claim": False,
        "profile_id": None,
        "display_name": None,
        "title_family": None,
        "confidence": float(confidence),
        "fail_closed_threshold": float(threshold),
        "evidence_count": int(evidence_count),
        "vlm_confidence": float(vlm_confidence),
        "ocr_confidence": float(ocr_confidence),
        "motion_confidence": float(motion_confidence),
        "hysteresis_state": hysteresis_state,
        "consecutive": int(consecutive),
        "stability_count": int(stability_count),
        "provenance": provenance or _default_provenance(),
        "no_claim_reason": why,
    }


def claim_record(
    *,
    session_id: str,
    clock_ns: int,
    session_head_ns: int | None,
    profile_id: str,
    display_name: str | None,
    confidence: float,
    threshold: float,
    consecutive: int,
    stability_count: int,
    evidence_count: int,
    vlm_confidence: float,
    ocr_confidence: float,
    motion_confidence: float,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "plane": PLANE,
        "session_id": session_id,
        "clock_ns": int(clock_ns),
        "session_head_ns": session_head_ns,
        "source_lobe": SOURCE_LOBE,
        "claim": True,
        "profile_id": str(profile_id),
        "display_name": display_name,
        "title_family": title_family_for(profile_id),
        "confidence": float(confidence),
        "fail_closed_threshold": float(threshold),
        "evidence_count": int(evidence_count),
        "vlm_confidence": float(vlm_confidence),
        "ocr_confidence": float(ocr_confidence),
        "motion_confidence": float(motion_confidence),
        "hysteresis_state": HYST_LOCKED,
        "consecutive": int(consecutive),
        "stability_count": int(stability_count),
        "provenance": provenance or _default_provenance(),
        "no_claim_reason": None,
    }


def record_valid(rec: dict[str, Any]) -> bool:
    return isinstance(rec, dict) and rec.get("plane") == PLANE


def _default_provenance() -> dict[str, Any]:
    return {
        "frame_source": "none",
        "sampling_mode": "sparse",
        "seq": None,
        "frame_clock_ns": None,
        "poll_interval_s": 3.0,
    }


_lv_lock = threading.Lock()
_lv_until = 0.0
_lv_reason = ""

LOCK_VERIFY_REASONS = frozenset(
    {
        "operator_profile",
        "first_visual",
        "menu_to_gameplay",
        "score_lock",
        "phrase_snap",
        "phrase_sprint",
        "title_flip",
    }
)


def request_lock_verify(reason: str, window_s: float = 6.0) -> None:
    """Process-local raised-rate window. Sparse default; never 60 Hz."""
    global _lv_until, _lv_reason
    why = str(reason or "").strip()
    if why not in LOCK_VERIFY_REASONS:
        why = "first_visual"
    now = time.time()
    until = now + max(1.0, float(window_s))
    with _lv_lock:
        if until > _lv_until:
            _lv_until = until
            _lv_reason = why


def lock_verify_active(now: float | None = None) -> tuple[bool, str]:
    t = time.time() if now is None else float(now)
    with _lv_lock:
        if t < _lv_until:
            return True, _lv_reason
        return False, ""


def canonical_record_bytes(rec: dict[str, Any]) -> bytes:
    body = {k: rec.get(k) for k in sorted(rec.keys()) if k != "ingredient"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def source_hash(rec: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_record_bytes(rec)).hexdigest()


def make_provenance(
    *,
    frame_source: str,
    sampling_mode: str,
    seq: int | None,
    frame_clock_ns: int | None,
    poll_interval_s: float,
) -> dict[str, Any]:
    return {
        "frame_source": frame_source,
        "sampling_mode": sampling_mode if sampling_mode in {"sparse", "lock_verify"} else "sparse",
        "seq": seq,
        "frame_clock_ns": frame_clock_ns,
        "poll_interval_s": float(poll_interval_s),
    }
