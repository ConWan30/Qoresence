"""Prediction lifecycle: arm → open → resolve | cancel on SessionTimeline.

Fast path arms; OCR/confirm resolves; stale arms cancel by TTL or lost pressure.
Does not invent scores. Helix open is policy-gated (not every fast chat).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

log = logging.getLogger(__name__)


class PredictionState(StrEnum):
    IDLE = "idle"
    ARMED = "armed"
    OPEN = "open"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


@dataclass
class PredictionLifecycleManager:
    """Source of truth for arm TTL / cancel; interops with MomentScorer Helix actions."""

    arm_ttl_s: float = 45.0
    open_on_arm: bool = False  # if True, try_open immediately when armed
    min_coupling_to_open: float = 0.55
    open_callback: Callable[[dict[str, Any]], bool] | None = None
    resolve_callback: Callable[[int], bool] | None = None

    state: PredictionState = PredictionState.IDLE
    armed_at: float = 0.0
    armed_meta: dict[str, Any] = field(default_factory=dict)
    open_meta: dict[str, Any] = field(default_factory=dict)
    last_reason: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def arm(
        self,
        *,
        coupling: float | None = None,
        frame_seq: int | None = None,
        buttons: list[str] | None = None,
        reason: str = "fast arm_prediction",
        clock_ns: int | None = None,
        auto_open: bool | None = None,
    ) -> PredictionState:
        """Fast path arm. Appends timeline kind=arm; opens drive."""
        with self._lock:
            if self.state in (PredictionState.OPEN,):
                # Already open — keep open, refresh meta lightly
                self.armed_meta.update(
                    {
                        "coupling": coupling,
                        "frame_seq": frame_seq,
                        "buttons": list(buttons or [])[:8],
                    }
                )
                return self.state

            self.state = PredictionState.ARMED
            self.armed_at = time.time()
            self.armed_meta = {
                "coupling": coupling,
                "frame_seq": frame_seq,
                "buttons": list(buttons or [])[:8],
                "reason": reason,
            }
            self.last_reason = reason
            self._timeline(
                kind="arm",
                path="fast",
                message="prediction armed",
                reason=reason,
                coupling=coupling,
                frame_seq=frame_seq,
                buttons=buttons,
                factual=False,
                clock_ns=clock_ns,
                open_drive=True,
            )

        do_open = self.open_on_arm if auto_open is None else bool(auto_open)
        if do_open:
            self.try_open(coupling=coupling, force=True, clock_ns=clock_ns)
        return self.state

    def try_open(
        self,
        *,
        coupling: float | None = None,
        force: bool = False,
        title: str = "Will they score on this drive?",
        clock_ns: int | None = None,
    ) -> PredictionState:
        """Policy: only open from armed when coupling high (or force)."""
        with self._lock:
            if self.state != PredictionState.ARMED:
                return self.state
            c = float(coupling if coupling is not None else self.armed_meta.get("coupling") or 0.0)
            if not force and c < self.min_coupling_to_open:
                return self.state

            opened = False
            if self.open_callback is not None:
                try:
                    opened = bool(
                        self.open_callback(
                            {
                                "title": title,
                                "outcomes": ["Yes", "No"],
                                "coupling": c,
                                **self.armed_meta,
                            }
                        )
                    )
                except Exception as e:
                    log.debug("prediction open_callback failed: %s", e)
                    opened = False
            else:
                # Local open (no Helix) — still track state for resolve/cancel
                opened = True

            if not opened and self.open_callback is not None:
                # Helix refused — stay armed
                return self.state

            self.state = PredictionState.OPEN
            self.open_meta = {"title": title, "coupling": c, "local": self.open_callback is None}
            self._timeline(
                kind="prediction_open",
                path="fast" if self.open_callback is None else "confirm",
                message=title,
                reason="prediction opened",
                coupling=c,
                frame_seq=self.armed_meta.get("frame_seq"),
                buttons=self.armed_meta.get("buttons"),
                factual=False,
                clock_ns=clock_ns,
            )
            return self.state

    def resolve(
        self,
        winning_outcome_index: int = 0,
        *,
        clock_ns: int | None = None,
        reason: str = "OCR score_changed",
    ) -> PredictionState:
        """Confirm path resolve. Works from armed or open (arm→resolve without open)."""
        with self._lock:
            if self.state not in (PredictionState.ARMED, PredictionState.OPEN):
                return self.state

            if self.state == PredictionState.OPEN and self.resolve_callback is not None:
                try:
                    self.resolve_callback(int(winning_outcome_index))
                except Exception as e:
                    log.debug("prediction resolve_callback failed: %s", e)

            prev = self.state
            self.state = PredictionState.RESOLVED
            self._timeline(
                kind="prediction_resolve",
                path="confirm",
                message=f"resolved winner={winning_outcome_index}",
                reason=reason,
                factual=True,
                clock_ns=clock_ns,
                close_drive=True,
                payload={
                    "winning_outcome_index": int(winning_outcome_index),
                    "from_state": str(prev),
                },
            )
            self._reset_soft()
            return PredictionState.RESOLVED

    def cancel(self, reason: str = "cancelled", *, clock_ns: int | None = None) -> PredictionState:
        with self._lock:
            if self.state in (
                PredictionState.IDLE,
                PredictionState.RESOLVED,
                PredictionState.CANCELLED,
            ):
                self.state = PredictionState.IDLE
                return self.state
            self.state = PredictionState.CANCELLED
            self.last_reason = reason
            self._timeline(
                kind="prediction_cancel",
                path="system",
                message="prediction cancelled",
                reason=reason,
                factual=False,
                clock_ns=clock_ns,
                close_drive=True,
            )
            self._reset_soft()
            return PredictionState.CANCELLED

    def tick(
        self,
        *,
        coupling: float | None = None,
        still_pressure_context: bool = True,
        clock_ns: int | None = None,
    ) -> PredictionState:
        """Expire arm TTL; cancel if pressure context lost while armed."""
        should_try_open = False
        with self._lock:
            if self.state == PredictionState.ARMED:
                age = time.time() - self.armed_at
                if age >= self.arm_ttl_s:
                    return self._cancel_locked("arm TTL expired", clock_ns=clock_ns)
                if not still_pressure_context:
                    return self._cancel_locked("pressure context lost", clock_ns=clock_ns)
                c = float(coupling if coupling is not None else 0.0)
                if c >= self.min_coupling_to_open:
                    should_try_open = True
            # OPEN stays until resolve (do not cancel Helix mid-flight on tick)
        if should_try_open and coupling is not None:
            self.try_open(coupling=coupling, clock_ns=clock_ns)
        return self.state

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": str(self.state),
                "armed_at": self.armed_at,
                "armed_meta": dict(self.armed_meta),
                "open_meta": dict(self.open_meta),
                "last_reason": self.last_reason,
                "arm_ttl_s": self.arm_ttl_s,
            }

    def _cancel_locked(self, reason: str, clock_ns: int | None = None) -> PredictionState:
        self.state = PredictionState.CANCELLED
        self.last_reason = reason
        self._timeline(
            kind="prediction_cancel",
            path="system",
            message="prediction cancelled",
            reason=reason,
            factual=False,
            clock_ns=clock_ns,
            close_drive=True,
        )
        self._reset_soft()  # → idle for next arm
        return self.state

    def _reset_soft(self) -> None:
        self.armed_at = 0.0
        self.armed_meta = {}
        self.open_meta = {}
        # Allow next arm: move to idle after brief resolved/cancelled
        self.state = PredictionState.IDLE

    @staticmethod
    def _timeline(**kwargs: Any) -> None:
        try:
            from qoresence.agents.session_timeline import get_session_timeline

            get_session_timeline().append(**kwargs)
        except Exception as e:
            log.debug("prediction timeline append failed: %s", e)


_mgr: PredictionLifecycleManager | None = None
_mgr_lock = threading.Lock()


def get_prediction_lifecycle() -> PredictionLifecycleManager:
    global _mgr
    with _mgr_lock:
        if _mgr is None:
            _mgr = PredictionLifecycleManager()
        return _mgr


def reset_prediction_lifecycle() -> PredictionLifecycleManager:
    global _mgr
    with _mgr_lock:
        _mgr = PredictionLifecycleManager()
        return _mgr
