"""Negative-evidence graph — emptiness licenses skip or redirect.

Nodes: no_frame | blank | overlay_rejected | below_threshold | dest_denied.
Blank / no_frame do not overlay a crop. dest_denied stays research ceremony.
"""

from __future__ import annotations

import threading
from typing import Any

from qoresence.graphs.flags import graph_enabled, note_applied
from qoresence.graphs.look_license import LookLicense, append_license, make_license

ABSENCE_KINDS = frozenset(
    {
        "no_frame",
        "blank",
        "overlay_rejected",
        "below_threshold",
        "dest_denied",
        "not_locked",
        "no_result",
        "feature_off",
        "plane_invalid",
    }
)

_lock = threading.Lock()
_last_license: LookLicense | None = None
_last_kind: str = ""
_skip: bool = False
_pause: bool = False


def reset() -> None:
    global _last_license, _last_kind, _skip, _pause
    with _lock:
        _last_license = None
        _last_kind = ""
        _skip = False
        _pause = False


def record_absence(
    kind: str,
    *,
    session_id: str = "",
    clock_ns: int | None = None,
    frame_seq: int | None = None,
) -> LookLicense | None:
    global _last_license, _last_kind, _skip, _pause
    if not graph_enabled("negative_evidence"):
        return None
    token = str(kind or "").strip()
    if token not in ABSENCE_KINDS:
        return None
    with _lock:
        if token == _last_kind and _last_license is not None:
            return _last_license

    skip = token in {"no_frame", "blank", "dest_denied", "feature_off", "plane_invalid"}
    pause = token in {"overlay_rejected"}
    lic_kind = "skip_look" if skip else "no_claim"
    permits: dict[str, Any] = {
        "next_action": "skip" if skip else ("crop" if pause else "no_claim"),
    }
    if pause:
        permits["crop_role"] = "pause"
        permits["next_action"] = "crop"
        lic_kind = "no_claim"
    refuses = (token,)
    if token == "dest_denied":
        # Research ceremony only — do not name a new wrap dest.
        permits["next_action"] = "skip"

    lic = make_license(
        graph="negative_evidence",
        kind=lic_kind,
        session_id=session_id,
        clock_ns=clock_ns,
        permits=permits,
        refuses=refuses,
        frame_seq=frame_seq,
    )
    if lic is None:
        return None
    with _lock:
        _last_license = lic
        _last_kind = token
        _skip = skip
        _pause = pause
    append_license(lic)
    note_applied(lic.id)
    if pause:
        try:
            from qoresence.graphs.crop_evidence import record_overlay_reject

            record_overlay_reject(None, clock_ns=clock_ns, session_id=session_id)
        except Exception:
            pass
    return lic


def skip_look() -> bool:
    if not graph_enabled("negative_evidence"):
        return False
    with _lock:
        return _skip


def pause_crops() -> bool:
    if not graph_enabled("negative_evidence"):
        return False
    with _lock:
        return _pause


def last_license() -> LookLicense | None:
    with _lock:
        return _last_license


def overlay_forbidden() -> bool:
    """Blank / no_frame must not become a crop overlay."""
    if not graph_enabled("negative_evidence"):
        return False
    with _lock:
        lic = _last_license
        skipped = _skip
    if lic is None:
        return False
    return skipped and any(r in {"blank", "no_frame"} for r in lic.refuses)
