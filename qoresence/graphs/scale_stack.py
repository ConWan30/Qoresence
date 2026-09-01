"""Multi-scale stack — which timescale may request the next look.

Escalate only: tick peek → phrase coupling → drive confirm → session wrap.
Confirm-path VLM is not licensed from tick scale alone.
"""

from __future__ import annotations

import threading
from typing import Any

from qoresence.graphs.flags import graph_enabled, note_applied
from qoresence.graphs.look_license import LookLicense, append_license, make_license

SCALES = ("tick", "phrase", "drive", "session")
SCALE_INDEX = {name: i for i, name in enumerate(SCALES)}

LOOK_FOR_SCALE = {
    "tick": "peek",
    "phrase": "coupling",
    "drive": "confirm",
    "session": "wrap",
}

KIND_FOR_SCALE = {
    "tick": "tick_peek",
    "phrase": "phrase_coupling",
    "drive": "drive_confirm",
    "session": "session_wrap",
}

# A look is allowed at ``scale`` only if scale index >= required index.
LOOK_MIN_SCALE = {
    "peek": "tick",
    "coupling": "phrase",
    "confirm": "drive",
    "wrap": "session",
}

_lock = threading.Lock()
_last_license: LookLicense | None = None
_licensed_scale: str = ""


def reset() -> None:
    global _last_license, _licensed_scale
    with _lock:
        _last_license = None
        _licensed_scale = ""


def license_scale(
    scale: str,
    *,
    look: str | None = None,
    lower_licensed: bool = False,
    session_id: str = "",
    clock_ns: int | None = None,
    frame_seq: int | None = None,
) -> LookLicense | None:
    """License a look at ``scale``. Escalate from a lower scale requires ``lower_licensed``."""
    global _last_license, _licensed_scale
    if not graph_enabled("scale_stack"):
        return None
    sc = str(scale or "").strip()
    if sc not in SCALE_INDEX:
        return None
    requested = str(look or LOOK_FOR_SCALE[sc]).strip()
    min_scale = LOOK_MIN_SCALE.get(requested)
    if min_scale is None:
        return None
    need = SCALE_INDEX[min_scale]
    have = SCALE_INDEX[sc]
    ok = have >= need
    if have > 0 and not lower_licensed and requested != LOOK_FOR_SCALE[sc]:
        # Escalating to a look above this scale's native look still needs a lower license
        # when the caller claims a higher look from a lower rung — handled by ``ok``.
        pass
    if sc != "tick" and not lower_licensed and requested in {"confirm", "wrap"}:
        # Drive/session confirm/wrap still allowed when this IS the native scale.
        if LOOK_FOR_SCALE[sc] != requested:
            ok = False
    if requested == "confirm" and sc == "tick":
        ok = False
    if requested == "confirm" and sc == "phrase":
        ok = False
    if requested == "wrap" and sc != "session":
        ok = False

    kind = KIND_FOR_SCALE[sc] if ok else "scale_refuse"
    permits: dict[str, Any] = {
        "next_action": requested if ok else "refuse",
        "scale": sc,
        "look": requested,
    }
    lic = make_license(
        graph="scale_stack",
        kind=kind,
        session_id=session_id,
        clock_ns=clock_ns,
        permits=permits,
        refuses=() if ok else (f"{sc}:{requested}",),
        frame_seq=frame_seq,
    )
    if lic is None:
        return None
    with _lock:
        _last_license = lic
        if ok:
            _licensed_scale = sc
    append_license(lic)
    note_applied(lic.id)
    return lic


def confirm_from_tick_alone() -> bool:
    """Always False when the graph is on; True (no extra gate) when off."""
    if not graph_enabled("scale_stack"):
        return True
    return False


def may_confirm(*, scale: str, lower_licensed: bool = False) -> bool:
    """Query-only: may this scale request a confirm look? No JSONL. Flag off → True."""
    if not graph_enabled("scale_stack"):
        return True
    sc = str(scale or "").strip()
    if sc not in SCALE_INDEX:
        return False
    if sc == "tick" or sc == "phrase":
        return False
    if sc == "drive":
        return True
    if sc == "session":
        return bool(lower_licensed)
    return False


def confirm_allowed(*, scale: str, lower_licensed: bool = False) -> bool:
    if not graph_enabled("scale_stack"):
        return True
    if not may_confirm(scale=scale, lower_licensed=lower_licensed):
        license_scale(scale, look="confirm", lower_licensed=lower_licensed)
        return False
    lic = license_scale(scale, look="confirm", lower_licensed=lower_licensed)
    return bool(lic is not None and lic.kind == "drive_confirm")


def last_license() -> LookLicense | None:
    with _lock:
        return _last_license


def licensed_scale() -> str:
    with _lock:
        return _licensed_scale


def note_tick_peek(*, session_id: str = "", frame_seq: int | None = None) -> None:
    """CIVIF tick is peek only. No JSONL. Does not upgrade a live phrase/drive."""
    global _licensed_scale
    if not graph_enabled("scale_stack"):
        return
    with _lock:
        if _licensed_scale in {"phrase", "drive", "session"}:
            return
        _licensed_scale = "tick"


def note_drive(*, session_id: str = "", frame_seq: int | None = None) -> LookLicense | None:
    """Drive opened — confirm look is now in scale. Call after timeline lock release."""
    if not graph_enabled("scale_stack"):
        return None
    return license_scale(
        "drive",
        look="confirm",
        lower_licensed=True,
        session_id=session_id,
        frame_seq=frame_seq,
    )


def note_drive_closed() -> None:
    """Drive closed — drop back to tick. No JSONL."""
    global _licensed_scale
    if not graph_enabled("scale_stack"):
        return
    with _lock:
        if _licensed_scale == "drive":
            _licensed_scale = "tick"


def note_session_wrap(*, session_id: str = "", frame_seq: int | None = None) -> LookLicense | None:
    """Session closeout — wrap look is now in scale. Call once per written closeout."""
    if not graph_enabled("scale_stack"):
        return None
    return license_scale(
        "session",
        look="wrap",
        lower_licensed=True,
        session_id=session_id,
        frame_seq=frame_seq,
    )
