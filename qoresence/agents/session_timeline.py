"""Session / drive causal memory on the shared observation clock.

Single long-lived log for two-speed moments, prediction lifecycle, and clip
chapters. Uses ``clock_ns`` (monotonic) — never Twitch delay.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_CAPACITY = 2000
DEFAULT_JSONL_DIR = Path("logs/timeline")


@dataclass
class TimelineEvent:
    clock_ns: int
    kind: str
    path: str = ""  # fast | confirm | system
    message: str = ""
    reason: str = ""
    frame_seq: int | None = None
    coupling: float | None = None
    buttons: list[str] = field(default_factory=list)
    factual: bool | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    drive_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Drop empties for compact snapshots
        if not d.get("buttons"):
            d.pop("buttons", None)
        if d.get("payload") == {}:
            d.pop("payload", None)
        if d.get("frame_seq") is None:
            d.pop("frame_seq", None)
        if d.get("coupling") is None:
            d.pop("coupling", None)
        if d.get("factual") is None:
            d.pop("factual", None)
        if not d.get("drive_id"):
            d.pop("drive_id", None)
        return d


@dataclass
class DriveSegment:
    drive_id: str
    started_ns: int
    ended_ns: int | None = None
    context: dict[str, Any] = field(default_factory=dict)
    event_indices: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "drive_id": self.drive_id,
            "started_ns": self.started_ns,
            "ended_ns": self.ended_ns,
            "context": self.context,
            "event_count": len(self.event_indices),
            "event_indices": list(self.event_indices[-32:]),
        }


class SessionTimeline:
    """Thread-safe causal event log + optional drive segments."""

    def __init__(
        self,
        capacity: int = DEFAULT_CAPACITY,
        *,
        persist: bool = False,
        persist_dir: Path | str | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._events: deque[TimelineEvent] = deque(maxlen=max(64, int(capacity)))
        self._drives: list[DriveSegment] = []
        self._active: DriveSegment | None = None
        self._drive_seq = 0
        self._persist = bool(persist)
        self._persist_dir = Path(persist_dir or DEFAULT_JSONL_DIR)
        self._jsonl: Path | None = None
        if self._persist:
            try:
                self._persist_dir.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%d_%H%M%S")
                self._jsonl = self._persist_dir / f"timeline_{stamp}.jsonl"
            except Exception as e:
                log.debug("timeline persist disabled: %s", e)
                self._persist = False

    def append(
        self,
        *,
        kind: str,
        path: str = "",
        message: str = "",
        reason: str = "",
        frame_seq: int | None = None,
        coupling: float | None = None,
        buttons: list[str] | None = None,
        factual: bool | None = None,
        payload: dict[str, Any] | None = None,
        clock_ns: int | None = None,
        open_drive: bool = False,
        close_drive: bool = False,
        drive_context: dict[str, Any] | None = None,
    ) -> TimelineEvent:
        """Append one causal event. Optionally open/close a drive segment."""
        now = int(clock_ns) if clock_ns is not None else time.monotonic_ns()
        with self._lock:
            if open_drive and self._active is None:
                self._drive_seq += 1
                did = f"drive_{self._drive_seq}"
                self._active = DriveSegment(
                    drive_id=did,
                    started_ns=now,
                    context=dict(drive_context or {}),
                )
                self._drives.append(self._active)

            drive_id = self._active.drive_id if self._active else None
            ev = TimelineEvent(
                clock_ns=now,
                kind=str(kind),
                path=str(path or ""),
                message=str(message or "")[:240],
                reason=str(reason or "")[:240],
                frame_seq=int(frame_seq) if frame_seq is not None else None,
                coupling=float(coupling) if coupling is not None else None,
                buttons=list(buttons or [])[:16],
                factual=factual,
                payload=dict(payload or {}),
                drive_id=drive_id,
            )
            self._events.append(ev)
            idx = len(self._events) - 1
            if self._active is not None:
                self._active.event_indices.append(idx)

            if close_drive and self._active is not None:
                self._active.ended_ns = now
                self._active = None

            if self._persist and self._jsonl is not None:
                try:
                    with self._jsonl.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
                except Exception:
                    pass
            return ev

    def recent(self, n: int = 20) -> list[TimelineEvent]:
        with self._lock:
            items = list(self._events)
        if n <= 0:
            return items
        return items[-n:]

    def why_last(self) -> dict[str, Any] | None:
        """Human-facing last fire summary for Deck why strip."""
        with self._lock:
            if not self._events:
                return None
            e = self._events[-1]
            btn = "·".join(e.buttons[:6]) if e.buttons else "—"
            coup = f"{e.coupling:.2f}" if e.coupling is not None else "—"
            seq = e.frame_seq if e.frame_seq is not None else "—"
            label = e.message or e.kind
            line = f"path={e.path or '—'} · coupling {coup} · {btn} · seq {seq} · {label}"
            return {
                "line": line,
                "kind": e.kind,
                "path": e.path,
                "message": e.message,
                "reason": e.reason,
                "frame_seq": e.frame_seq,
                "coupling": e.coupling,
                "buttons": list(e.buttons),
                "factual": e.factual,
                "clock_ns": e.clock_ns,
                "drive_id": e.drive_id,
            }

    def active_drive(self) -> DriveSegment | None:
        with self._lock:
            return self._active

    def drives(self) -> list[DriveSegment]:
        with self._lock:
            return list(self._drives)

    def events_in_window(self, t0_ns: int, t1_ns: int) -> list[TimelineEvent]:
        if t1_ns < t0_ns:
            t0_ns, t1_ns = t1_ns, t0_ns
        with self._lock:
            return [e for e in self._events if t0_ns <= e.clock_ns <= t1_ns]

    def snapshot(self, recent_n: int = 40) -> dict[str, Any]:
        with self._lock:
            events = [e.to_dict() for e in list(self._events)[-recent_n:]]
            drives = [d.to_dict() for d in self._drives[-12:]]
            active = self._active.to_dict() if self._active else None
            active_obj = self._active
            last_drive_obj = self._drives[-1] if self._drives else None
        why = self.why_last()
        # DriveGraph enrichment (optional; never break snapshot)
        drive_graph_summary = None
        why_graph_line = None
        try:
            from qoresence.agents.drive_graph import DriveGraph

            drive = active_obj or last_drive_obj
            if drive is not None:
                g = DriveGraph.from_timeline_drive(self, drive)
                if g is not None and g.nodes:
                    drive_graph_summary = g.summary()
                    why_graph_line = g.why_line()
        except Exception:
            drive_graph_summary = None
            why_graph_line = None

        # Prefer graph-backed why line when available
        if why is not None and why_graph_line:
            why = dict(why)
            why["line"] = why_graph_line
            why["source"] = "drive_graph"
            if drive_graph_summary:
                why["phase"] = drive_graph_summary.get("phase")
                cl = drive_graph_summary.get("climax") or {}
                why["climax_score"] = cl.get("score")
                why["best_label"] = cl.get("best_label")
        elif why is None and why_graph_line:
            why = {
                "line": why_graph_line,
                "source": "drive_graph",
                "phase": (drive_graph_summary or {}).get("phase"),
            }

        out: dict[str, Any] = {
            "events": events,
            "drives": drives,
            "active_drive": active,
            "why_last": why,
            "count": len(events),
        }
        if drive_graph_summary is not None:
            out["drive_graph"] = drive_graph_summary
        return out

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._drives.clear()
            self._active = None
            self._drive_seq = 0


_timeline: SessionTimeline | None = None
_timeline_lock = threading.Lock()


def get_session_timeline(*, persist: bool | None = None) -> SessionTimeline:
    """Process-wide timeline singleton."""
    global _timeline
    with _timeline_lock:
        if _timeline is None:
            do_persist = bool(persist) if persist is not None else False
            try:
                import os

                if os.environ.get("QORESENCE_TIMELINE_PERSIST", "0") == "1":
                    do_persist = True
            except Exception:
                pass
            _timeline = SessionTimeline(persist=do_persist)
        return _timeline


def reset_session_timeline() -> SessionTimeline:
    """Test helper — replace singleton."""
    global _timeline
    with _timeline_lock:
        _timeline = SessionTimeline(persist=False)
        return _timeline
