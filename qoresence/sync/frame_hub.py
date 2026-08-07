"""FrameHub re-export for two-speed ClutchBot / IVC scaffold.

Canonical implementation lives in ``qoresence.monitor.frame_hub`` (streamer +
monitor). This module provides the sync-package API surface:

  publish(frame) / get_frame_hub().publish(frame)
  get_latest_meta() -> {seq, clock_ns, has_frame}
"""

from __future__ import annotations

from typing import Any

from qoresence.monitor.frame_hub import (
    FrameHub,
    get_frame_hub,
    get_latest,
    get_latest_stamp,
    publish,
)

__all__ = [
    "FrameHub",
    "get_frame_hub",
    "get_latest",
    "get_latest_meta",
    "get_latest_stamp",
    "publish",
]


def get_latest_meta() -> dict[str, Any]:
    """Cheap stamp dict: seq, clock_ns, has_frame (no frame copy)."""
    st = get_latest_stamp()
    return {
        "seq": int(st.get("seq") or 0),
        "clock_ns": int(st.get("clock_ns") or 0),
        "has_frame": bool(st.get("has_frame")),
        "age_s": st.get("age_s"),
    }
