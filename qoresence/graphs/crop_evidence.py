"""Crop-region evidence graph — reorder existing scorebug bands only.

Nodes are profile + band box + role. Do not invent new crop numbers.
"""

from __future__ import annotations

import threading
from typing import Any

from qoresence.graphs.flags import graph_enabled, note_applied
from qoresence.graphs.look_license import LookLicense, append_license, make_license

ROLES = ("primary", "tight", "pause", "ticker")

_lock = threading.Lock()
_prefer_index: int | None = None
_pause_only: bool = False
_fallback_from: int | None = None
_profile: str = ""
_last_license: LookLicense | None = None


def reset() -> None:
    global _prefer_index, _pause_only, _fallback_from, _profile, _last_license
    with _lock:
        _prefer_index = None
        _pause_only = False
        _fallback_from = None
        _profile = ""
        _last_license = None


def roles_for(
    profile: str | object | None,
    bands: tuple[tuple[float, float, float, float], ...],
) -> tuple[str, ...]:
    madden = "madden" in str(profile or "").lower()
    out: list[str] = []
    for i, _band in enumerate(bands):
        if i == 0:
            out.append("primary")
        elif madden and i in (1, 2):
            out.append("ticker")
        elif (not madden) and i == 1:
            out.append("tight")
        else:
            out.append("pause")
    return tuple(out)


def record_lock(
    profile: str | object | None,
    *,
    crop_index: int | None = None,
    crop: list[float] | tuple[float, ...] | None = None,
    bands: tuple[tuple[float, float, float, float], ...] | None = None,
    ticket_id: str = "",
    clock_ns: int | None = None,
    session_id: str = "",
    crop_hash: str = "",
    frame_seq: int | None = None,
) -> LookLicense | None:
    if not graph_enabled("crop_evidence"):
        return None
    idx = _resolve_index(crop_index, crop, bands)
    if idx is None:
        idx = 0
    return _commit(
        "crop_prefer",
        profile,
        prefer=idx,
        pause_only=False,
        fallback_from=None,
        ticket_id=ticket_id,
        clock_ns=clock_ns,
        session_id=session_id,
        crop_hash=crop_hash,
        frame_seq=frame_seq,
        crop=_as_crop(crop) or (list(bands[idx]) if bands and 0 <= idx < len(bands) else None),
    )


def record_ticker_null(
    profile: str | object | None,
    *,
    from_index: int = 0,
    bands: tuple[tuple[float, float, float, float], ...] | None = None,
    clock_ns: int | None = None,
    session_id: str = "",
) -> LookLicense | None:
    if not graph_enabled("crop_evidence"):
        return None
    nxt = int(from_index) + 1
    n = len(bands) if bands else 0
    if n and nxt >= n:
        nxt = min(int(from_index), n - 1)
    return _commit(
        "crop_fallback",
        profile,
        prefer=nxt,
        pause_only=False,
        fallback_from=int(from_index),
        clock_ns=clock_ns,
        session_id=session_id,
        crop=list(bands[nxt]) if bands and 0 <= nxt < len(bands) else None,
    )


def record_pause_menu(
    profile: str | object | None,
    *,
    clock_ns: int | None = None,
    session_id: str = "",
) -> LookLicense | None:
    if not graph_enabled("crop_evidence"):
        return None
    return _commit(
        "crop_pause",
        profile,
        prefer=None,
        pause_only=True,
        fallback_from=None,
        clock_ns=clock_ns,
        session_id=session_id,
    )


def record_overlay_reject(
    profile: str | object | None,
    **kw: Any,
) -> LookLicense | None:
    return record_pause_menu(profile, **kw)


def licensed_crops(
    profile: str | object | None,
    base: tuple[tuple[float, float, float, float], ...],
) -> tuple[tuple[float, float, float, float], ...] | None:
    """Reorder ``base`` when this graph has evidence. None → caller keeps ``base``."""
    if not graph_enabled("crop_evidence"):
        return None
    if not base:
        return None
    with _lock:
        prefer = _prefer_index
        pause_only = _pause_only
        fallback_from = _fallback_from
        marked = _profile
    if marked and profile and _family(marked) != _family(str(profile)):
        return None
    roles = roles_for(profile, base)
    if pause_only:
        pause = [base[i] for i, r in enumerate(roles) if r == "pause"]
        rest = [base[i] for i, r in enumerate(roles) if r != "pause"]
        if not pause:
            return None
        out = tuple(pause + rest)
        return out if out != base else None
    idx = prefer
    if idx is None and fallback_from is not None:
        idx = int(fallback_from) + 1
    if idx is None or idx < 0 or idx >= len(base):
        return None
    chosen = base[idx]
    rest = [b for i, b in enumerate(base) if i != idx]
    out = (chosen, *rest)
    return out if out != base else None


def last_license() -> LookLicense | None:
    with _lock:
        return _last_license


def _commit(
    kind: str,
    profile: str | object | None,
    *,
    prefer: int | None,
    pause_only: bool,
    fallback_from: int | None,
    ticket_id: str = "",
    clock_ns: int | None = None,
    session_id: str = "",
    crop_hash: str = "",
    frame_seq: int | None = None,
    crop: list[float] | None = None,
) -> LookLicense | None:
    global _prefer_index, _pause_only, _fallback_from, _profile, _last_license
    role = "pause" if pause_only else ("primary" if prefer == 0 else "tight")
    if kind == "crop_fallback":
        role = "ticker"
    permits: dict[str, Any] = {
        "next_action": "crop",
        "crop_role": role,
        "keep_crop": kind == "crop_prefer",
        "profile": str(profile or ""),
    }
    if prefer is not None:
        permits["crop_index"] = int(prefer)
    if crop is not None:
        permits["crop"] = list(crop)
        if ticket_id:
            permits["constraint_kind"] = "crop_band"
    lic = make_license(
        graph="crop_evidence",
        kind=kind,
        session_id=session_id,
        clock_ns=clock_ns,
        permits=permits,
        source_ticket_id=ticket_id,
        frame_seq=frame_seq,
        crop_hash=crop_hash,
    )
    if lic is None:
        return None
    with _lock:
        _prefer_index = prefer
        _pause_only = pause_only
        _fallback_from = fallback_from
        _profile = str(profile or "")
        _last_license = lic
    append_license(lic)
    note_applied(lic.id)
    if ticket_id and crop is not None:
        _maybe_learning_crop(lic, ticket_id, crop, str(profile or ""), session_id, clock_ns)
    return lic


def _maybe_learning_crop(
    lic: LookLicense,
    ticket_id: str,
    crop: list[float],
    profile: str,
    session_id: str,
    clock_ns: int | None,
) -> None:
    try:
        from qoresence.agents.learning_edge import enabled as learning_on
        from qoresence.agents.learning_edge import maybe_record_on_resolve
        from qoresence.graphs.flags import enabled as look_on
        from qoresence.vision.confirm_ticket import get_ticket_book

        if not look_on() or not learning_on():
            return
        ticket = get_ticket_book().get(ticket_id) or get_ticket_book().latest()
        maybe_record_on_resolve(
            ticket=ticket,
            profile=profile,
            crop=crop,
            frame_seq=lic.frame_seq,
            session_id=session_id or lic.session_id,
        )
    except Exception:
        pass


def _resolve_index(
    crop_index: int | None,
    crop: list[float] | tuple[float, ...] | None,
    bands: tuple[tuple[float, float, float, float], ...] | None,
) -> int | None:
    if crop_index is not None:
        try:
            return int(crop_index)
        except (TypeError, ValueError):
            return None
    box = _as_crop(crop)
    if box is None or not bands:
        return None
    for i, b in enumerate(bands):
        try:
            if [float(x) for x in b] == box:
                return i
        except (TypeError, ValueError):
            continue
    return None


def _as_crop(band: Any) -> list[float] | None:
    if not isinstance(band, (list, tuple)) or len(band) != 4:
        return None
    try:
        x1, x2, y1, y2 = (float(band[0]), float(band[1]), float(band[2]), float(band[3]))
    except (TypeError, ValueError):
        return None
    if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
        return None
    return [x1, x2, y1, y2]


def _family(profile: str) -> str:
    return "madden" if "madden" in profile.lower() else "cfb"
