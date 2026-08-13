"""Temporal bind: visual onset ↔ HID onset (observation plane).

Forked from QorTroller ``l9_presence/event_bind.py`` *schema only*.
No record_hash, no PoAC. Mode is always TEMPORAL — clock proximity with
an honest label. A bind is coupling, not authorship.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

DEFAULT_BIND_WINDOW_MS = 400.0


@dataclass
class VisualOnset:
    clock_ns: int
    kind: str
    frame_seq: int | None = None
    label: str = ""


@dataclass
class HidOnset:
    clock_ns: int
    name: str
    kind: str = "press"
    frame_seq: int | None = None
    imu_precursor_ms: float | None = None


@dataclass
class EventBind:
    mode: str
    hid_name: str
    hid_kind: str
    hid_clock_ns: int
    visual_kind: str
    visual_clock_ns: int
    lag_ms: float
    imu_precursor_ms: float | None
    frame_seq: int | None
    visual_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def bind_onsets(
    visuals: Iterable[VisualOnset],
    hids: Iterable[HidOnset],
    *,
    window_ms: float = DEFAULT_BIND_WINDOW_MS,
) -> list[EventBind]:
    """Pair each visual onset to the nearest preceding HID onset in the window."""
    hid_list = sorted(hids, key=lambda h: h.clock_ns)
    used: set[int] = set()
    out: list[EventBind] = []
    win_ns = int(max(20.0, window_ms) * 1e6)
    for vis in sorted(visuals, key=lambda v: v.clock_ns):
        best: HidOnset | None = None
        best_dt = win_ns + 1
        for i, hid in enumerate(hid_list):
            if i in used:
                continue
            dt = vis.clock_ns - hid.clock_ns
            if dt < 0 or dt > win_ns:
                continue
            if dt < best_dt:
                best = hid
                best_dt = dt
        if best is None:
            continue
        used.add(hid_list.index(best))
        out.append(
            EventBind(
                mode="TEMPORAL",
                hid_name=best.name,
                hid_kind=best.kind,
                hid_clock_ns=best.clock_ns,
                visual_kind=vis.kind,
                visual_clock_ns=vis.clock_ns,
                lag_ms=round(best_dt / 1e6, 3),
                imu_precursor_ms=best.imu_precursor_ms,
                frame_seq=vis.frame_seq if vis.frame_seq is not None else best.frame_seq,
                visual_label=vis.label,
            )
        )
    return out


class EventBinder:
    """Process-local onset logs for live IVC / Ghost Cut."""

    def __init__(self, max_n: int = 256) -> None:
        self._lock = threading.Lock()
        self._visual: list[VisualOnset] = []
        self._hid: list[HidOnset] = []
        self._max = max_n

    def push_visual(self, onset: VisualOnset) -> None:
        with self._lock:
            self._visual.append(onset)
            self._visual = self._visual[-self._max :]

    def push_hid(self, onset: HidOnset) -> None:
        with self._lock:
            self._hid.append(onset)
            self._hid = self._hid[-self._max :]

    def recent(self, window_ms: float = DEFAULT_BIND_WINDOW_MS) -> list[EventBind]:
        with self._lock:
            return bind_onsets(list(self._visual), list(self._hid), window_ms=window_ms)

    def last_lag_ms(self) -> float | None:
        binds = self.recent()
        if not binds:
            return None
        return binds[-1].lag_ms


_binder = EventBinder()


def get_event_binder() -> EventBinder:
    return _binder
