"""Input–Video Coupler package — observation-plane only.

Lazy exports so importing hid_report from the controller thread cannot
deadlock against a concurrent `import qoresence.sync.ivc`.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "EventBind",
    "EventBinder",
    "FrameHub",
    "ImuRing",
    "InputEvent",
    "InputRing",
    "InputVideoCoupler",
    "get_event_binder",
    "get_frame_hub",
    "get_imu_ring",
    "get_input_ring",
    "get_ivc",
    "get_last_coupling",
    "get_latest_meta",
    "pack_usb_report",
    "parse_report",
    "publish_frame",
    "push_input",
    "start_ivc",
    "stop_ivc",
    "HapticProbe",
    "start_haptic_probe",
    "stop_haptic_probe",
]

_LAZY = {
    "EventBind": ("qoresence.sync.event_bind", "EventBind"),
    "EventBinder": ("qoresence.sync.event_bind", "EventBinder"),
    "get_event_binder": ("qoresence.sync.event_bind", "get_event_binder"),
    "FrameHub": ("qoresence.sync.frame_hub", "FrameHub"),
    "get_frame_hub": ("qoresence.sync.frame_hub", "get_frame_hub"),
    "get_latest_meta": ("qoresence.sync.frame_hub", "get_latest_meta"),
    "publish_frame": ("qoresence.sync.frame_hub", "publish"),
    "pack_usb_report": ("qoresence.sync.hid_report", "pack_usb_report"),
    "parse_report": ("qoresence.sync.hid_report", "parse_report"),
    "ImuRing": ("qoresence.sync.imu_ring", "ImuRing"),
    "get_imu_ring": ("qoresence.sync.imu_ring", "get_imu_ring"),
    "InputEvent": ("qoresence.sync.input_ring", "InputEvent"),
    "InputRing": ("qoresence.sync.input_ring", "InputRing"),
    "get_input_ring": ("qoresence.sync.input_ring", "get_input_ring"),
    "push_input": ("qoresence.sync.input_ring", "push"),
    "InputVideoCoupler": ("qoresence.sync.ivc", "InputVideoCoupler"),
    "get_ivc": ("qoresence.sync.ivc", "get_ivc"),
    "get_last_coupling": ("qoresence.sync.ivc", "get_last_coupling"),
    "start_ivc": ("qoresence.sync.ivc", "start_ivc"),
    "stop_ivc": ("qoresence.sync.ivc", "stop_ivc"),
    "HapticProbe": ("qoresence.sync.haptic_probe", "HapticProbe"),
    "start_haptic_probe": ("qoresence.sync.haptic_probe", "start_haptic_probe"),
    "stop_haptic_probe": ("qoresence.sync.haptic_probe", "stop_haptic_probe"),
}


def __getattr__(name: str) -> Any:
    spec = _LAZY.get(name)
    if spec is None:
        raise AttributeError(name)
    mod_name, attr = spec
    import importlib

    return getattr(importlib.import_module(mod_name), attr)
