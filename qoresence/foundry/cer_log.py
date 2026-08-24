"""Live Coupled Event Record ring — observation plane only.

IVC calls ``observe_coupling`` after it releases its lock. This module must
only enqueue (same class as OTel Rule 5): no bus emit, no lobe locks, no
blocking disk on the IVC thread.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from collections import deque
from pathlib import Path
from typing import Any

from qoresence.core.civif_tick import CoupledTickRecord, build_coupled_tick

log = logging.getLogger(__name__)

_log: CerLog | None = None
_log_lock = threading.Lock()


def _session_id() -> str:
    try:
        from qoresence.core.session import SessionAuthority

        ident = SessionAuthority.current()
        if ident is not None:
            return str(ident.session_id or "")
    except Exception:
        pass
    return os.getenv("QORESENCE_SESSION_ID") or ""


def _edges_since(prev_ns: int, now_ns: int) -> list[Any]:
    if now_ns <= 0:
        return []
    t0 = prev_ns + 1 if prev_ns > 0 else max(0, now_ns - 40_000_000)
    try:
        from qoresence.sync.input_ring import get_input_ring

        return get_input_ring().in_window(t0, now_ns)
    except Exception:
        return []


class CerLog:
    def __init__(self, *, maxlen: int = 240, jsonl_path: Path | None = None) -> None:
        self._ring: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._q: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=128)
        self._n = 0
        self._last_clock = 0
        self._jsonl = jsonl_path
        self._worker = threading.Thread(target=self._run, name="civif-cer", daemon=True)
        self._worker.start()

    def observe(self, coupling: dict[str, Any]) -> None:
        coup = dict(coupling or {})
        now_ns = int(coup.get("video_clock_ns") or 0)
        with self._lock:
            prev = self._last_clock
        edges = _edges_since(prev, now_ns)
        rec_obj: CoupledTickRecord = build_coupled_tick(
            coupling=coup,
            events=edges,
            session_id=_session_id(),
        )
        rec = rec_obj.to_dict()
        with self._lock:
            self._ring.append(rec)
            if now_ns > 0:
                self._last_clock = now_ns
            self._n += 1
            n = self._n
        try:
            from qoresence.foundry.civif_metrics import observe_tick

            observe_tick(rec)
        except Exception:
            pass
        if n % 10 != 0:
            return
        try:
            self._q.put_nowait(rec)
        except queue.Full:
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(rec)
            except queue.Full:
                pass

    def last(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._ring:
                return None
            return dict(self._ring[-1])

    def recent(self, n: int = 40) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._ring)
        return rows[-max(1, min(200, int(n))) :]

    def _run(self) -> None:
        path = self._jsonl
        while True:
            rec = self._q.get()
            if rec is None:
                return
            if path is None:
                continue
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, default=str) + "\n")
            except Exception as e:
                log.debug("civif jsonl: %s", e)


def _default_jsonl() -> Path | None:
    sid = os.getenv("QORESENCE_SESSION_ID") or "session"
    return Path("logs") / "civif" / f"{sid}.jsonl"


def get_cer_log() -> CerLog:
    global _log
    with _log_lock:
        if _log is None:
            _log = CerLog(jsonl_path=_default_jsonl())
        return _log


def observe_coupling(coupling: dict[str, Any]) -> None:
    get_cer_log().observe(coupling)


def live_record() -> dict[str, Any] | None:
    return get_cer_log().last()
