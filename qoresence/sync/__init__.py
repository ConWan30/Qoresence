"""Input–Video Coupler package — observation-plane only.

InputRing holds recent HID edges; IVC joins them to FrameHub frame stamps.
Controller default OFF; no second capture device.
"""

from qoresence.sync.frame_hub import (
    FrameHub,
    get_frame_hub,
    get_latest_meta,
)
from qoresence.sync.frame_hub import (
    publish as publish_frame,
)
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
    "FrameHub",
    "InputEvent",
    "InputRing",
    "InputVideoCoupler",
    "get_frame_hub",
    "get_input_ring",
    "get_ivc",
    "get_last_coupling",
    "get_latest_meta",
    "publish_frame",
    "push_input",
    "start_ivc",
    "stop_ivc",
]
