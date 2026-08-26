"""Haptic observation records — plane, licenses, empty/no-claim shape.

Observation only. A haptic pulse is never a confirmed gameplay event,
score license, HID identity, or ``controller_bodied`` bit.
"""

from __future__ import annotations

from typing import Any

HAPTIC_PLANE = "qoresence-observation"
HAPTIC_SCHEMA = "haptic_obs-1"
SOURCE_LOBE = "controller"

KINDS = frozenset({"haptic_transient", "haptic_unavailable", "haptic_dropout"})
QUALIFICATIONS = frozenset({"candidate", "observed"})
INTENSITY_BUCKETS = frozenset({"low", "mid", "high"})
LICENSE_KEYS = (
    "haptics_observed",
    "haptics_coupled",
    "haptics_signature_known",
    "haptics_confirmed",
)


def intensity_bucket(intensity_01: float | None) -> str | None:
    """Coarse amplitude bucket. Never returns raw device units."""
    if intensity_01 is None:
        return None
    x = max(0.0, min(1.0, float(intensity_01)))
    if x < 0.22:
        return "low"
    if x < 0.62:
        return "mid"
    return "high"


def licenses_fail_closed(
    *,
    observed: bool = False,
    coupled: bool = False,
    signature_known: bool = False,  # noqa: ARG001 — locked false in Phase 0–1
    confirmed: bool = False,  # noqa: ARG001 — locked false in Phase 0–1
) -> dict[str, bool]:
    """Staged licenses. Signature/confirm stay false until a later operator GO."""
    obs = bool(observed)
    return {
        "haptics_observed": obs,
        "haptics_coupled": bool(coupled) and obs,
        "haptics_signature_known": False,
        "haptics_confirmed": False,
    }


def empty_record(
    *,
    session_id: str = "",
    clock_ns: int = 0,
    reason: str = "channel_unavailable",
    connection_mode: str = "none",
) -> dict[str, Any]:
    """No-claim shape when the channel is missing. Not a synthetic zero pulse."""
    return {
        "schema_version": HAPTIC_SCHEMA,
        "plane": HAPTIC_PLANE,
        "session_id": str(session_id or ""),
        "clock_ns": int(clock_ns or 0),
        "source_lobe": SOURCE_LOBE,
        "kind": "haptic_unavailable",
        "t_start_ns": None,
        "t_end_ns": None,
        "duration_ms": None,
        "intensity": None,
        "intensity_01": None,
        "channel": None,
        "actuators": [],
        "coupled": False,
        "signature": None,
        "qualification": "candidate",
        "licenses": licenses_fail_closed(),
        "provenance": {
            "connection_mode": connection_mode or "none",
            "reason": str(reason or "channel_unavailable"),
            "coupling_reason": "unattributed",
            "video_clock_ns": None,
            "frame_seq": None,
            "ivc_dt_ms": None,
            "in_ivc_window": False,
            "coupling": None,
        },
    }


def validate_record(rec: dict[str, Any]) -> list[str]:
    """Return human-readable problems. Empty list = acceptable observation record."""
    errs: list[str] = []
    if not isinstance(rec, dict):
        return ["not_a_dict"]
    if rec.get("plane") != HAPTIC_PLANE:
        errs.append("plane")
    if rec.get("schema_version") != HAPTIC_SCHEMA:
        errs.append("schema_version")
    if rec.get("source_lobe") != SOURCE_LOBE:
        errs.append("source_lobe")
    if rec.get("kind") not in KINDS:
        errs.append("kind")
    if rec.get("qualification") not in QUALIFICATIONS:
        errs.append("qualification")
    if "controller_bodied" in rec:
        errs.append("controller_bodied_forbidden")
    lic = rec.get("licenses")
    if not isinstance(lic, dict):
        errs.append("licenses")
    else:
        for k in LICENSE_KEYS:
            if k not in lic:
                errs.append(f"license_{k}")
        if lic.get("haptics_signature_known"):
            errs.append("signature_known_not_phase01")
        if lic.get("haptics_confirmed"):
            errs.append("confirmed_not_phase01")
    if rec.get("kind") == "haptic_unavailable":
        if rec.get("t_start_ns") is not None or rec.get("intensity") is not None:
            errs.append("unavailable_must_be_empty")
        if rec.get("licenses", {}).get("haptics_observed"):
            errs.append("unavailable_observed")
    return errs
