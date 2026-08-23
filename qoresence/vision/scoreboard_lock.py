"""Scoreboard lock worker — extract off the LIVE / subscriber thread.

Callers only copy a frame and apply the last result. Heavy HUD/OCR runs
on ``scoreboard-lock``. Never emits bus events. Never takes a lobe lock.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import numpy as np

from qoresence.vision.visual_context import VisualContext

log = logging.getLogger(__name__)

_APPLY_FIELDS = (
    "home_score",
    "away_score",
    "quarter",
    "down",
    "yards_to_go",
    "play_clock",
    "clock_seconds",
    "score_vlm_locked",
    "confirm_ticket_id",
    "home_team",
    "away_team",
    "home_left",
    "home_color",
    "away_color",
    "home_logo",
    "away_logo",
)

_OCR_INTERVAL_S = 1.0


class ScoreboardLockWorker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending_frame: np.ndarray | None = None
        self._pending_ctx: VisualContext | None = None
        self._latest: VisualContext | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._gen = 0
        self._done_gen = 0
        self._last_ocr = 0.0
        self._thread: threading.Thread | None = None

    def offer(self, frame: np.ndarray, ctx: VisualContext | None) -> VisualContext:
        try:
            if frame is None or not hasattr(frame, "shape") or len(frame.shape) < 2:
                return self.apply(ctx)
            snap = np.ascontiguousarray(frame)
            if snap is frame:
                snap = frame.copy()
        except Exception:
            return self.apply(ctx)
        seed = _seed_ctx(ctx)
        with self._lock:
            self._pending_frame = snap
            self._pending_ctx = seed
            self._gen += 1
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(
                    target=self._loop, name="scoreboard-lock", daemon=True
                )
                self._thread.start()
        self._wake.set()
        return self.apply(ctx)

    def apply(self, ctx: VisualContext | None) -> VisualContext:
        if ctx is None:
            ctx = VisualContext()
        with self._lock:
            last = self._latest
        if last is None:
            return ctx
        for name in _APPLY_FIELDS:
            setattr(ctx, name, getattr(last, name))
        if isinstance(getattr(last, "details", None), dict):
            if not isinstance(ctx.details, dict):
                ctx.details = {}
            ticket = last.details.get("confirm_ticket")
            if ticket is not None:
                ctx.details["confirm_ticket"] = ticket
        return ctx

    def wait(self, timeout_s: float = 2.0) -> bool:
        target = self._gen
        deadline = time.time() + max(0.05, float(timeout_s))
        while time.time() < deadline:
            with self._lock:
                if self._done_gen >= target and target > 0:
                    return True
            time.sleep(0.01)
        return False

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=1.5)
        with self._lock:
            self._pending_frame = None
            self._pending_ctx = None
            self._latest = None
            self._gen = 0
            self._done_gen = 0
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=0.5)
            self._wake.clear()
            if self._stop.is_set():
                return
            with self._lock:
                frame = self._pending_frame
                seed = self._pending_ctx
                gen = self._gen
            if frame is None:
                continue
            try:
                from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor

                allow_ocr = False
                now = time.time()
                try:
                    from qoresence.vision.scoreboard_ocr_engine import get_scoreboard_engine

                    eng = get_scoreboard_engine()
                    if eng.is_ready() and (now - self._last_ocr) >= _OCR_INTERVAL_S:
                        allow_ocr = True
                        self._last_ocr = now
                except Exception:
                    allow_ocr = False
                ext = FootballScoreboardExtractor()
                out = ext.extract(frame, seed, allow_ocr=allow_ocr)
            except Exception as e:
                log.debug("scoreboard lock worker: %s", e)
                out = seed
            with self._lock:
                self._latest = out
                self._done_gen = gen


def _seed_ctx(ctx: VisualContext | None) -> VisualContext:
    if ctx is None:
        return VisualContext()
    try:
        return VisualContext.from_dict(ctx.to_dict())
    except Exception:
        return VisualContext(
            game_category=getattr(ctx, "game_category", None),
            game_state=getattr(ctx, "game_state", None),
            game_profile=str(getattr(ctx, "game_profile", "") or ""),
        )


_worker: ScoreboardLockWorker | None = None
_worker_lock = threading.Lock()


def get_scoreboard_lock_worker() -> ScoreboardLockWorker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = ScoreboardLockWorker()
        return _worker


def reset_scoreboard_lock_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None:
            _worker.stop()
        _worker = ScoreboardLockWorker()


def offer_scoreboard_frame(frame: Any, ctx: VisualContext | None = None) -> VisualContext:
    return get_scoreboard_lock_worker().offer(frame, ctx)


def apply_scoreboard_lock(ctx: VisualContext | None) -> VisualContext:
    return get_scoreboard_lock_worker().apply(ctx)


def wait_scoreboard_lock(timeout_s: float = 2.0) -> bool:
    return get_scoreboard_lock_worker().wait(timeout_s)
