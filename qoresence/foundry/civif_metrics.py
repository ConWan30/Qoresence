"""In-memory CIVIF observation metrics.

Called from the CER enqueue path and highlight ranking. Must stay cheap:
no bus emit, no lobe locks, no disk, no network.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

_lock = threading.Lock()
_by_session: dict[str, CivifSessionMetrics] = {}


@dataclass
class CivifSessionMetrics:
    session_id: str
    ticks: int = 0
    board_locked_ticks: int = 0
    controller_bodied_any: bool = False
    highlight_count: int = 0
    highlight_sum: float = 0.0
    highlight_min: float | None = None
    highlight_max: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        n = self.ticks
        hn = self.highlight_count
        return {
            "session_id": self.session_id,
            "tick_count": n,
            "board_locked_ticks": self.board_locked_ticks,
            "board_locked_rate": (self.board_locked_ticks / n) if n else 0.0,
            "controller_bodied_any": bool(self.controller_bodied_any),
            "highlight_coupling": {
                "count": hn,
                "min": self.highlight_min,
                "max": self.highlight_max,
                "mean": (self.highlight_sum / hn) if hn else None,
            },
        }


def reset_metrics() -> None:
    with _lock:
        _by_session.clear()


def observe_tick(rec: dict[str, Any] | None) -> None:
    if not isinstance(rec, dict):
        return
    sid = str(rec.get("session_id") or "") or "_"
    locked = bool(rec.get("board_locked"))
    bodied = bool(rec.get("controller_bodied"))
    with _lock:
        row = _by_session.get(sid)
        if row is None:
            row = CivifSessionMetrics(session_id=sid)
            _by_session[sid] = row
        row.ticks += 1
        if locked:
            row.board_locked_ticks += 1
        if bodied:
            row.controller_bodied_any = True


def observe_highlight_scores(scores: list[float], *, session_id: str = "") -> None:
    sid = str(session_id or "") or "_"
    vals: list[float] = []
    for raw in scores or []:
        try:
            vals.append(float(raw))
        except (TypeError, ValueError):
            continue
    if not vals:
        return
    with _lock:
        row = _by_session.get(sid)
        if row is None:
            row = CivifSessionMetrics(session_id=sid)
            _by_session[sid] = row
        for v in vals:
            row.highlight_count += 1
            row.highlight_sum += v
            row.highlight_min = v if row.highlight_min is None else min(row.highlight_min, v)
            row.highlight_max = v if row.highlight_max is None else max(row.highlight_max, v)


def snapshot(session_id: str | None = None) -> dict[str, Any]:
    with _lock:
        if session_id is not None:
            row = _by_session.get(str(session_id) or "_")
            return row.to_dict() if row else {"session_id": session_id, "tick_count": 0}
        return {k: v.to_dict() for k, v in _by_session.items()}
