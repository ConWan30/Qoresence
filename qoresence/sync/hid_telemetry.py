"""HID telemetry slot — newest-wins latest-state for tremor/stick.

High-rate analog telemetry is *state*, not events. The controller publishes
here every report (a cheap dict swap under a short lock — same class as the
FrameHub latest-frame slot); consumers poll on their own cadence. The bus
then carries coalesced aggregates at the sync-health emit ceiling instead of
per-report floods.

Observation plane: no bus emits, no lobe locks, no blocking.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_tremor: dict[str, Any] | None = None
_stick: dict[str, dict[str, Any]] = {}
_counts: dict[str, int] = {"tremor": 0, "stick": 0, "reports": 0}
_started_mono = time.monotonic()


def publish_tremor(*, gyro: list[int], accel: list[int], clock_ns: int) -> None:
    global _tremor
    with _lock:
        _tremor = {"gyro": list(gyro), "accel": list(accel), "clock_ns": int(clock_ns)}
        _counts["tremor"] += 1


def publish_stick(
    *, stick: str, x: float, y: float, dx: float, dy: float, clock_ns: int
) -> None:
    with _lock:
        _stick[stick] = {
            "x": float(x),
            "y": float(y),
            "dx": float(dx),
            "dy": float(dy),
            "clock_ns": int(clock_ns),
        }
        _counts["stick"] += 1


def note_report() -> None:
    """One call per HID report — cheap eps denominator."""
    with _lock:
        _counts["reports"] += 1


def snapshot() -> dict[str, Any]:
    with _lock:
        uptime = max(time.monotonic() - _started_mono, 1e-6)
        return {
            "tremor": dict(_tremor) if _tremor else None,
            "stick": {k: dict(v) for k, v in _stick.items()},
            "counts": dict(_counts),
            "tremor_eps": round(_counts["tremor"] / uptime, 1),
            "stick_eps": round(_counts["stick"] / uptime, 1),
            "reports_eps": round(_counts["reports"] / uptime, 1),
        }


def reset() -> None:
    """Tests: clear slots and counters."""
    global _tremor, _started_mono
    with _lock:
        _tremor = None
        _stick.clear()
        for k in _counts:
            _counts[k] = 0
        _started_mono = time.monotonic()
