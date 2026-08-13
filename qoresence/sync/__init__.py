"""Input–Video Coupler package — observation-plane only.

InputRing holds recent HID edges; IVC joins them to FrameHub frame stamps.
Controller default OFF; no second capture device.
"""

from qoresence.sync.event_bind import EventBind, EventBinder, get_event_binder
from qoresence.sync.frame_hub import (
    FrameHub,
    get_frame_hub,
    get_latest_meta,
)
from qoresence.sync.frame_hub import (
    publish as publish_frame,
)
from qoresence.sync.hid_report import pack_usb_report, parse_report
from qoresence.sync.imu_ring import ImuRing, get_imu_ring
from qoresence.sync.input_ring import InputEvent, InputRing, get_input_ring
from qoresence.sync.input_ring import push as push_input
from qoresence.sync.ivc import (
    InputVideoCoupler,
    get_ivc,
    get_last_coupling,
    start_ivc,
    stop_ivc,
)

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
]
