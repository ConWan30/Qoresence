"""
Phase 4 Tests — Controller Lobe

Synthetic tests using fake HID device to verify event emission,
rolling buffer, causal_parent_ns, trigger onset detection, stick motion.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from qoresence.core import (
    ControllerConfig,
    EventType,
    RetinaEventBus,
    SessionAuthority,
    SourceLobe,
)
from qoresence.lobes.controller import ControllerRuntime, get_controller_runtime, list_controllers


class FakeHIDDevice:
    """Fake hid.Device for testing without hardware.

    Mimics the hidapi device API: instantiate, then call open() or open_path(),
    then read(max_length, timeout_ms).
    """

    def __init__(self, reports: list[bytes]):
        self._reports = reports
        self._idx = 0
        self._closed = False
        self._opened = False

    def open(
        self, vendor_id: int = 0, product_id: int = 0, serial_number: str | None = None
    ) -> None:
        self._opened = True

    def open_path(self, path: bytes) -> None:
        self._opened = True

    def read(self, max_length: int, timeout_ms: int = 0) -> list[int] | None:
        if self._closed or not self._opened or self._idx >= len(self._reports):
            return None
        report = self._reports[self._idx]
        self._idx += 1
        return list(report)

    def close(self) -> None:
        self._closed = True

    def set_nonblocking(self, v: int) -> None:
        pass


def _make_dualsense_report(
    buttons: int = 0,
    l2: int = 0,
    r2: int = 0,
    lx: int = 128,
    ly: int = 128,
    rx: int = 128,
    ry: int = 128,
    gyro: tuple[int, int, int] = (0, 0, 0),
    accel: tuple[int, int, int] = (0, 0, 0),
    battery: int = 100,
    usb_state: int = 1,
) -> bytes:
    """Create a synthetic DualSense USB 0x01 report (canonical offsets)."""
    from qoresence.sync.hid_report import pack_usb_report

    return pack_usb_report(
        buttons=buttons,
        l2=l2,
        r2=r2,
        lx=lx,
        ly=ly,
        rx=rx,
        ry=ry,
        gyro=gyro,
        accel=accel,
    )
