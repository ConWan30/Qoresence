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

from qoresence.core.coupled_event import (
    CIVIF_PLANE,
    CIVIF_SCHEMA,
    current_situation,
    input_bodied,
)

log = logging.getLogger(__name__)

_log: CerLog | None = None
_log_lock = threading.Lock()


class CerLog:
    def __init__(self, *, maxlen: int = 240, jsonl_path: Path | None = None) -> None:
        self._ring: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._q: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=128)
        self._n = 0
        self._jsonl = jsonl_path
        self._worker = threading.Thread(target=self._run, name="civif-cer", daemon=True)
        self._worker.start()

    def observe(self, coupling: dict[str, Any]) -> None:
        coup = dict(coupling or {})
        evs: list[dict[str, Any]] = []
        bodied, reason = input_bodied(evs, coup)
        rec = {
            "schema_version": CIVIF_SCHEMA,
            "plane": CIVIF_PLANE,
            "kind": "live_tick",
            "video": {
                "t_start_ns": int(coup.get("video_clock_ns") or 0),
                "t_end_ns": int(coup.get("video_clock_ns") or 0),
                "frame_seq": int(coup.get("frame_seq") or 0),
            },
            "input": {"bodied": bodied, "events": evs, "reason": reason},
            "situation": current_situation(),
            "coupling": coup,
        }
        with self._lock:
            self._ring.append(rec)
            self._n += 1
            n = self._n
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
