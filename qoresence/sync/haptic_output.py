"""DualSense HID *output* rumble bytes (emulated / inject path).

USB 0x02 and BT 0x31 maps follow the community DualSense output layout.
This module never writes to a device. Live DualSense-on-PS5 does not
expose these bytes to the laptop — treat as unavailable unless something
feeds ``observe_output_report``.
"""

from __future__ import annotations

from typing import Any


def pack_output_report(
    *,
    rumble_right: int = 0,
    rumble_left: int = 0,
    transport: str = "usb",
) -> bytes:
    """Synthetic output report for tests / inject. Does not open HID."""
    rr = max(0, min(255, int(rumble_right)))
    rl = max(0, min(255, int(rumble_left)))
    if str(transport).lower() in {"bt", "bluetooth"}:
        raw = bytearray(78)
        raw[0] = 0x31
        raw[1] = 0x02
        raw[2] = 0xFF
        raw[3] = 0xF7
        raw[4] = rr
        raw[5] = rl
        return bytes(raw)
    raw = bytearray(48)
    raw[0] = 0x02
    raw[1] = 0xFF
    raw[2] = 0xF7
    raw[3] = rr
    raw[4] = rl
    return bytes(raw)


def parse_output_rumble(raw: bytes) -> dict[str, Any] | None:
    """Return rumble L/R if this looks like a DualSense output report."""
    if not raw:
        return None
    rid = raw[0]
    if rid == 0x02 and len(raw) >= 5:
        return {
            "transport": "usb",
            "rumble_right": int(raw[3]),
            "rumble_left": int(raw[4]),
        }
    if rid == 0x31 and len(raw) >= 6 and raw[1] == 0x02:
        return {
            "transport": "bt",
            "rumble_right": int(raw[4]),
            "rumble_left": int(raw[5]),
        }
    return None
