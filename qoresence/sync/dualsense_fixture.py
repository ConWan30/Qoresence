"""Software DualSense — drive the real HID / IMU / bind path without hardware.

Observation plane only. A fixture is a canned USB 0x01 report stream, not a
claim about a physical pad.
"""

from __future__ import annotations

from typing import Any

from qoresence.core import clock_ns
from qoresence.sync.event_bind import VisualOnset, bind_onsets, get_event_binder
from qoresence.sync.hid_report import R2, pack_usb_report


def feed_bodied_r2(
    runtime: Any,
    *,
    t0_ns: int | None = None,
    precursor_ms: float = 20.0,
    visual_kind: str = "score_changed",
    visual_lag_ms: float = 60.0,
) -> dict[str, Any]:
    """Idle → IMU jolt → analog R2 → visual onset. Returns bind snapshot."""
    get_event_binder().clear()
    t0 = int(t0_ns if t0_ns is not None else clock_ns())
    jolt_ns = t0 + int(5e6)
    press_ns = t0 + int(max(6.0, precursor_ms) * 1e6)
    vis_ns = press_ns + int(max(10.0, visual_lag_ms) * 1e6)

    for i in range(8):
        runtime.ingest_report(
            pack_usb_report(gyro=(5, 5, 5), accel=(0, 0, 1000)),
            host_ts_ns=t0 - int((120 - i) * 1e6),
        )
    runtime.ingest_report(pack_usb_report(gyro=(5, 5, 5), accel=(0, 0, 1000)), host_ts_ns=t0)
    runtime.ingest_report(
        pack_usb_report(gyro=(80, 10, 10), accel=(0, 0, 1000)),
        host_ts_ns=jolt_ns,
    )
    runtime.ingest_report(
        pack_usb_report(r2=50, gyro=(20, 5, 5), accel=(0, 0, 1000)),
        host_ts_ns=press_ns,
    )
    runtime.ingest_report(
        pack_usb_report(buttons=R2, r2=180, gyro=(12, 4, 4), accel=(0, 0, 1000)),
        host_ts_ns=press_ns + int(1e6),
    )

    binder = get_event_binder()
    binder.push_visual(VisualOnset(clock_ns=vis_ns, kind=visual_kind, label="fixture"))
    binds = binder.recent(window_ms=400.0)
    last = binds[-1] if binds else None
    return {
        "ok": last is not None,
        "press_ns": press_ns,
        "visual_ns": vis_ns,
        "binds": [b.to_dict() for b in binds],
        "last_bind": last.to_dict() if last else None,
        "imu_bodied": bool(last and last.imu_precursor_ms is not None) if last else False,
    }


def bind_fixture_onsets(visuals, hids, *, window_ms: float = 400.0):
    """Thin wrapper so tests can bind canned clocks without a runtime."""
    return bind_onsets(visuals, hids, window_ms=window_ms)
