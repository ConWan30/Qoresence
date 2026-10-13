"""Same-Seq join graph — which frame_seq may be looked at.

Cheap read of LivePaint / seq windows. Never copies BGR. Never emits bus events.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from qoresence.deck.live_paint import SAME_SEQ_SLACK
from qoresence.graphs.flags import graph_enabled, note_applied
from qoresence.graphs.look_license import LookLicense, append_license, make_license

_lock = threading.Lock()
_last_license: LookLicense | None = None
_last_sig: tuple[str, int, int, int] | None = None
_last_appended_kind: str | None = None
_last_appended_ok: bool | None = None
_last_appended_live_seq: int = 0
_last_appended_clock_ns: int = 0

_QUIET_KINDS = frozenset({"join_ok", "slack_hold"})
_LOUD_KINDS = frozenset({"seq_skew", "plane_dim"})


def _jsonl_min_ns() -> int:
    try:
        return max(0, int(float(os.environ.get("QORESENCE_LOOK_SAME_SEQ_JSONL_MIN_NS", "1000000000"))))
    except (TypeError, ValueError):
        return 1_000_000_000


def _jsonl_every_seq() -> int:
    try:
        return max(1, int(float(os.environ.get("QORESENCE_LOOK_SAME_SEQ_JSONL_EVERY_SEQ", "30"))))
    except (TypeError, ValueError):
        return 30


def reset() -> None:
    global _last_license, _last_sig
    global _last_appended_kind, _last_appended_ok, _last_appended_live_seq, _last_appended_clock_ns
    with _lock:
        _last_license = None
        _last_sig = None
        _last_appended_kind = None
        _last_appended_ok = None
        _last_appended_live_seq = 0
        _last_appended_clock_ns = 0


def _should_append_jsonl(
    kind: str,
    ok: bool,
    live: int,
    clock_ns: int,
) -> bool:
    if kind in _LOUD_KINDS:
        return True
    if kind not in _QUIET_KINDS:
        return True
    if _last_appended_kind is None:
        return True
    if _last_appended_kind != kind or _last_appended_ok is not ok:
        return True
    min_ns = _jsonl_min_ns()
    if min_ns > 0 and clock_ns > 0 and _last_appended_clock_ns > 0:
        if clock_ns - _last_appended_clock_ns >= min_ns:
            return True
    every = _jsonl_every_seq()
    if live > 0 and _last_appended_live_seq > 0:
        if live - _last_appended_live_seq >= every:
            return True
    return False


def _note_appended(kind: str, ok: bool, live: int, clock_ns: int) -> None:
    global _last_appended_kind, _last_appended_ok, _last_appended_live_seq, _last_appended_clock_ns
    _last_appended_kind = kind
    _last_appended_ok = ok
    _last_appended_live_seq = int(live)
    _last_appended_clock_ns = int(clock_ns)


def classify_join(
    *,
    live_seq: int = 0,
    widget_seq: int = 0,
    hid_seq: int = 0,
    plane_dim: bool = False,
    same_seq: bool | None = None,
    slack: int = SAME_SEQ_SLACK,
    session_id: str = "",
    clock_ns: int | None = None,
) -> LookLicense | None:
    global _last_license, _last_sig
    if not graph_enabled("same_seq_join"):
        return None
    live = int(live_seq or 0)
    widget = int(widget_seq or 0)
    hid = int(hid_seq or 0)
    slack_n = max(0, int(slack))
    hid_skew = hid > 0 and live > 0 and abs(live - hid) > slack_n
    if plane_dim:
        kind = "plane_dim"
        ok = False
    elif same_seq is False or hid_skew:
        kind = "seq_skew"
        ok = False
    elif live <= 0:
        kind = "seq_skew"
        ok = False
    else:
        delta = abs(live - widget) if widget > 0 else 0
        if widget > 0 and delta > slack_n:
            kind = "seq_skew"
            ok = False
        elif widget > 0 and delta > 0:
            kind = "slack_hold"
            ok = True
        else:
            kind = "join_ok"
            ok = True
    sig = (kind, live, widget, hid)
    ts_ns = int(clock_ns if clock_ns is not None else time.time_ns())
    with _lock:
        if _last_sig == sig and _last_license is not None:
            return _last_license
        permits: dict[str, Any] = {
            "next_action": "look" if ok else "refuse",
            "frame_seq": live,
        }
        refuses = () if ok else (kind,)
        lic = make_license(
            graph="same_seq_join",
            kind=kind,
            session_id=session_id,
            clock_ns=ts_ns,
            permits=permits,
            refuses=refuses,
            frame_seq=live,
        )
        if lic is None:
            return None
        _last_license = lic
        _last_sig = sig
        if _should_append_jsonl(kind, ok, live, ts_ns):
            append_license(lic)
            _note_appended(kind, ok, live, ts_ns)
            note_applied(lic.id)
    return lic


def record_live_paint(paint: Any, *, session_id: str = "", clock_ns: int | None = None) -> LookLicense | None:
    if paint is None:
        return None
    hid = 0
    if graph_enabled("same_seq_join"):
        try:
            from qoresence.sync.hid_seq_line import get_hid_seq_line

            sample = get_hid_seq_line().latest()
            if sample is not None:
                hid = int(getattr(sample, "hub_seq", 0) or 0)
        except Exception:
            hid = 0
    return classify_join(
        live_seq=int(getattr(paint, "live_seq", 0) or 0),
        widget_seq=int(getattr(paint, "widget_seq", 0) or 0),
        hid_seq=hid,
        plane_dim=bool(getattr(paint, "plane_dim", False)),
        same_seq=bool(getattr(paint, "same_seq", False)),
        session_id=session_id,
        clock_ns=clock_ns,
    )


def confirm_look_allowed(license: LookLicense | None = None) -> bool:
    """Confirm-path VLM / EasyOCR only when join_ok or slack_hold. Flag off → True."""
    if not graph_enabled("same_seq_join"):
        return True
    lic = license if license is not None else last_license()
    if lic is None:
        return True
    return lic.kind in {"join_ok", "slack_hold"}


def coupling_mint_allowed(
    *,
    same_seq: bool | None = None,
    plane_dim: bool = False,
    live_seq: int = 0,
    widget_seq: int = 0,
) -> bool:
    """Coupling ticket extra gate. Flag off or unknown seq → True (existing fail-closed)."""
    if not graph_enabled("same_seq_join"):
        return True
    if plane_dim:
        classify_join(live_seq=live_seq, widget_seq=widget_seq, plane_dim=True, same_seq=same_seq)
        return False
    if same_seq is False:
        classify_join(live_seq=live_seq, widget_seq=widget_seq, plane_dim=False, same_seq=False)
        return False
    if same_seq is None and live_seq <= 0:
        return True
    lic = classify_join(
        live_seq=live_seq,
        widget_seq=widget_seq,
        plane_dim=plane_dim,
        same_seq=same_seq,
    )
    return confirm_look_allowed(lic)


def last_license() -> LookLicense | None:
    with _lock:
        return _last_license
