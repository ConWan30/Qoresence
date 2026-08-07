"""Input–Video Coupler package — observation-plane only.

InputRing holds recent HID edges; IVC joins them to FrameHub frame stamps.
Controller default OFF; no second capture device.
"""

from qoresence.sync.input_ring import InputEvent, InputRing, get_input_ring, push as push_input
from qoresence.sync.ivc import (
    InputVideoCoupler,
    get_ivc,
    get_last_coupling,
    start_ivc,
    stop_ivc,
)

__all__ = [
    "InputEvent",
    "InputRing",
    "InputVideoCoupler",
    "get_input_ring",
    "get_ivc",
    "get_last_coupling",
    "push_input",
    "start_ivc",
    "stop_ivc",
]
