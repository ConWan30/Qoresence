"""Transport-aware DualSense / DualSense Edge HID parser.

Forked from QorTroller ``controller/hid_report_parser.py`` for the
observation plane only — no PoAC, no chain. USB report 0x01 (64 B) and
Bluetooth report 0x31 (78 B, +1 field shift). IMU is raw int16.

USB offsets (community DualSense Edge map, live-verified in QorTroller):
  lx=1 ly=2 rx=3 ry=4 l2=5 r2=6 buttons_0=8 buttons_1=9
  gyro xyz = 16,18,20  accel xyz = 22,24,26
"""

from __future__ import annotations

import enum
import struct
from typing import Any


class TransportType(enum.Enum):
    USB = "usb"
    BLUETOOTH = "bt"
    UNKNOWN = "unknown"


USB_OFFSETS: dict[str, int] = {
    "lx": 1,
    "ly": 2,
    "rx": 3,
    "ry": 4,
    "l2": 5,
    "r2": 6,
    "buttons_0": 8,
    "buttons_1": 9,
    "gyro_x": 16,
    "gyro_y": 18,
    "gyro_z": 20,
    "accel_x": 22,
    "accel_y": 24,
    "accel_z": 26,
}

BT_OFFSETS: dict[str, int] = {k: v + 1 for k, v in USB_OFFSETS.items()}

# DualSense face/shoulder bits → Qoresence internal ControllerRuntime.Buttons
_B0_SQUARE = 0x10
_B0_CROSS = 0x20
_B0_CIRCLE = 0x40
_B0_TRIANGLE = 0x80
_B1_L1 = 0x01
_B1_R1 = 0x02
_B1_L2 = 0x04
_B1_R2 = 0x08
_B1_CREATE = 0x10
_B1_OPTIONS = 0x20
_B1_L3 = 0x40
_B1_R3 = 0x80

# Internal masks (must match lobes.controller.Buttons)
CROSS = 1 << 0
CIRCLE = 1 << 1
SQUARE = 1 << 2
TRIANGLE = 1 << 3
L1 = 1 << 4
R1 = 1 << 5
L2 = 1 << 6
R2 = 1 << 7
CREATE = 1 << 8
OPTIONS = 1 << 9
L3 = 1 << 10
R3 = 1 << 11


def detect_transport(raw: bytes) -> TransportType:
    if len(raw) >= 64 and raw[0] == 0x01:
        return TransportType.USB
    if len(raw) >= 78 and raw[0] == 0x31:
        return TransportType.BLUETOOTH
    return TransportType.UNKNOWN


def dualsense_bytes_to_internal(b0: int, b1: int) -> int:
    mask = 0
    if b0 & _B0_SQUARE:
        mask |= SQUARE
    if b0 & _B0_CROSS:
        mask |= CROSS
    if b0 & _B0_CIRCLE:
        mask |= CIRCLE
    if b0 & _B0_TRIANGLE:
        mask |= TRIANGLE
    if b1 & _B1_L1:
        mask |= L1
    if b1 & _B1_R1:
        mask |= R1
    if b1 & _B1_L2:
        mask |= L2
    if b1 & _B1_R2:
        mask |= R2
    if b1 & _B1_CREATE:
        mask |= CREATE
    if b1 & _B1_OPTIONS:
        mask |= OPTIONS
    if b1 & _B1_L3:
        mask |= L3
    if b1 & _B1_R3:
        mask |= R3
    return mask


def internal_to_dualsense_bytes(mask: int) -> tuple[int, int]:
    b0 = 0
    b1 = 0
    if mask & SQUARE:
        b0 |= _B0_SQUARE
    if mask & CROSS:
        b0 |= _B0_CROSS
    if mask & CIRCLE:
        b0 |= _B0_CIRCLE
    if mask & TRIANGLE:
        b0 |= _B0_TRIANGLE
    if mask & L1:
        b1 |= _B1_L1
    if mask & R1:
        b1 |= _B1_R1
    if mask & L2:
        b1 |= _B1_L2
    if mask & R2:
        b1 |= _B1_R2
    if mask & CREATE:
        b1 |= _B1_CREATE
    if mask & OPTIONS:
        b1 |= _B1_OPTIONS
    if mask & L3:
        b1 |= _B1_L3
    if mask & R3:
        b1 |= _B1_R3
    return b0, b1


def parse_report(raw: bytes, transport: TransportType | None = None) -> dict[str, Any]:
    if transport is None:
        transport = detect_transport(raw)
    off = BT_OFFSETS if transport == TransportType.BLUETOOTH else USB_OFFSETS

    def _u8(key: str) -> int:
        idx = off[key]
        return raw[idx] if len(raw) > idx else 0

    def _i16(key: str) -> int:
        idx = off[key]
        if len(raw) >= idx + 2:
            return struct.unpack_from("<h", raw, idx)[0]
        return 0

    b0 = _u8("buttons_0")
    b1 = _u8("buttons_1")
    return {
        "transport": transport.value,
        "lx": _u8("lx"),
        "ly": _u8("ly"),
        "rx": _u8("rx"),
        "ry": _u8("ry"),
        "l2": _u8("l2"),
        "r2": _u8("r2"),
        "buttons_0": b0,
        "buttons_1": b1,
        "buttons": dualsense_bytes_to_internal(b0, b1),
        "gyro_x": _i16("gyro_x"),
        "gyro_y": _i16("gyro_y"),
        "gyro_z": _i16("gyro_z"),
        "accel_x": _i16("accel_x"),
        "accel_y": _i16("accel_y"),
        "accel_z": _i16("accel_z"),
    }


def pack_usb_report(
    *,
    buttons: int = 0,
    l2: int = 0,
    r2: int = 0,
    lx: int = 128,
    ly: int = 128,
    rx: int = 128,
    ry: int = 128,
    gyro: tuple[int, int, int] = (0, 0, 0),
    accel: tuple[int, int, int] = (0, 0, 0),
) -> bytes:
    """Synthetic USB 0x01 report for tests. ``buttons`` is the *internal* mask."""
    raw = bytearray(64)
    raw[0] = 0x01
    raw[1] = lx & 0xFF
    raw[2] = ly & 0xFF
    raw[3] = rx & 0xFF
    raw[4] = ry & 0xFF
    raw[5] = l2 & 0xFF
    raw[6] = r2 & 0xFF
    b0, b1 = internal_to_dualsense_bytes(buttons)
    raw[8] = b0
    raw[9] = b1
    struct.pack_into("<hhh", raw, 16, *gyro)
    struct.pack_into("<hhh", raw, 22, *accel)
    return bytes(raw)
