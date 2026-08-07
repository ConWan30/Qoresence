"""
Qoresence Controller Lobe — Phase 4

Local HID capture for DualShock Edge (and generic controllers).
Rolling buffer + causal_parent_ns stamping for cross-lobe correlation.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import hid

from qoresence.core import (
    ControllerConfig,
    EventType,
    RetinaEventBus,
    SourceLobe,
    clock_ns,
)

# hidapi uses lowercase 'device' class on Windows
HIDDevice = hid.device

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# DUALSHOCK EDGE HID CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

# Sony DualShock Edge (CFI-ZCP1)
DS_EDGE_VID = 0x054C  # Sony
DS_EDGE_PID = 0x0CE6  # DualSense Edge

# Generic DualSense (for fallback)
DS_PID = 0x0CE6

# Report IDs
REPORT_ID_INPUT = 0x01
REPORT_ID_OUTPUT = 0x02
REPORT_ID_FEATURE = 0x03

# Input report size (standard DualSense)
INPUT_REPORT_SIZE = 64


# ──────────────────────────────────────────────────────────────────────────────
# CONTROLLER STATE
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class ControllerState:
    """Decoded controller state from HID report."""

    # Buttons (bitmask)
    buttons: int = 0
    # Triggers (0-255)
    l2: int = 0
    r2: int = 0
    # Sticks (0-255, centered at 128)
    lx: int = 128
    ly: int = 128
    rx: int = 128
    ry: int = 128
    # IMU (if available in report)
    gyro_x: int = 0
    gyro_y: int = 0
    gyro_z: int = 0
    accel_x: int = 0
    accel_y: int = 0
    accel_z: int = 0
    # Battery / misc
    battery: int = 0
    usb_state: int = 0
    # Timestamp
    device_ts: int = 0
    host_ts_ns: int = 0


# Button bitmasks (DualSense standard layout)
class Buttons:
    CROSS = 1 << 0  # South
    CIRCLE = 1 << 1  # East
    SQUARE = 1 << 2  # West
    TRIANGLE = 1 << 3  # North
    L1 = 1 << 4
    R1 = 1 << 5
    L2 = 1 << 6
    R2 = 1 << 7
    CREATE = 1 << 8  # Share
    OPTIONS = 1 << 9  # Options
    L3 = 1 << 10
    R3 = 1 << 11
    PS = 1 << 12
    TOUCHPAD = 1 << 13
    MUTE = 1 << 14  # Mic mute
    FN_LEFT = 1 << 15  # Left function (Edge)
    FN_RIGHT = 1 << 16  # Right function (Edge)


# ──────────────────────────────────────────────────────────────────────────────
# ROLLING BUFFER ENTRY
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class BufferEntry:
    """Entry in the causal rolling buffer."""

    clock_ns: int
    source_lobe: SourceLobe
    event_type: EventType
    payload: dict
    causal_parent_ns: int | None = None


# ──────────────────────────────────────────────────────────────────────────────
# CONTROLLER RUNTIME
# ──────────────────────────────────────────────────────────────────────────────


class ControllerRuntime:
    """
    HID capture loop for DualShock Edge / generic controllers.

    - Opens device by VID/PID or path
    - Reads input reports at poll_rate_hz
    - Decodes buttons, triggers, sticks, IMU
    - Emits controller_event, trigger_onset, stick_motion, tremor_sample
    - Maintains rolling buffer for causal_parent_ns correlation
    - Writes presence touch file for streamer lobe sync
    """

    def __init__(
        self,
        config: ControllerConfig,
        bus: RetinaEventBus,
        session_head_ns: int,
        presence_touch_file: Path | None = None,
    ):
        self.config = config
        self.bus = bus
        self.session_head_ns = session_head_ns

        # Presence touch file for streamer sync
        self.presence_touch_file = presence_touch_file or Path("logs/controller_presence.touch")
        self.presence_touch_file.parent.mkdir(parents=True, exist_ok=True)

        # HID device
        self._device: hid.Device | None = None
        self._device_path: str | None = None

        # State
        self._running = False
        self._thread: threading.Thread | None = None
        self._prev_state = ControllerState()

        # Rolling buffer for causal correlation
        self._buffer = deque(maxlen=config.buffer_size)

        # Trigger onset detection
        self._prev_l2 = 0
        self._prev_r2 = 0
        self._trigger_threshold = 30  # ~12% press

        # Stats
        self._reports_read = 0
        self._start_time = 0.0

        # Presence callback (for fusion engine)
        self._presence_callback: callable | None = None

        # Track last trigger/stick values for cross-lobe coupling
        self._last_trigger_value = 0.0
        self._last_stick_motion = 0.0
        self._causal_density = 0
        self._last_event_ns = 0

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Open HID device and start capture thread."""
        if self._running:
            log.warning("ControllerRuntime already running")
            return True

        if not self._open_device():
            return False

        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(
            target=self._run_loop, name="qoresence-controller", daemon=True
        )
        self._thread.start()

        log.info(
            f"Controller lobe started: {self._device_path}, "
            f"poll_rate={self.config.poll_rate_hz}Hz, buffer={self.config.buffer_size}"
        )
        return True

    def stop(self) -> None:
        """Stop capture thread and close device."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
        log.info("Controller lobe stopped")

    def is_running(self) -> bool:
        return self._running

    def set_presence_callback(self, callback: callable) -> None:
        """Set callback for presence status updates (for fusion engine)."""
        self._presence_callback = callback

    def get_stats(self) -> dict:
        """Get controller statistics for cross-lobe coupling."""
        return {
            "last_trigger": self._last_trigger_value
            if hasattr(self, "_last_trigger_value")
            else 0.0,
            "stick_motion": self._last_stick_motion if hasattr(self, "_last_stick_motion") else 0.0,
            "causal_density": self._causal_density if hasattr(self, "_causal_density") else 0,
            "last_event_ns": self._last_event_ns if hasattr(self, "_last_event_ns") else 0,
        }

    def get_last_state(self) -> dict:
        """Get last controller state for cross-modal verification."""
        return {
            "causal_density": self._causal_density if hasattr(self, "_causal_density") else 0,
            "last_trigger": self._last_trigger_value
            if hasattr(self, "_last_trigger_value")
            else 0.0,
        }

    def get_buffer_snapshot(self) -> list[BufferEntry]:
        """Get copy of rolling buffer for cross-lobe correlation."""
        return list(self._buffer)

    def find_causal_parent(self, max_age_ns: int = 50_000_000) -> int | None:
        """
        Find most recent controller event within max_age_ns for causal_parent_ns.

        Returns clock_ns of the parent event or None.
        """
        now = clock_ns()
        for entry in reversed(self._buffer):
            if now - entry.clock_ns <= max_age_ns:
                return entry.clock_ns
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # DEVICE MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────

    def _open_device(self) -> bool:
        """Open HID device by VID/PID or path."""
        try:
            self._device = HIDDevice()

            # Priority 1: Explicit path
            if self.config.device_path:
                self._device.open_path(self.config.device_path.encode())
                self._device_path = self.config.device_path
                return True

            # Priority 2: Explicit VID/PID
            vid = self.config.device_vid or DS_EDGE_VID
            pid = self.config.device_pid or DS_EDGE_PID
            self._device.open(vid, pid)
            self._device_path = f"vid={vid:04x},pid={pid:04x}"
            return True

        except Exception as e:
            log.error(f"Failed to open HID device: {e}")
            self._device = None
            return False

    def _enumerate_devices(self) -> list[dict]:
        """List all HID devices for debugging."""
        devices = []
        for d in hid.enumerate():
            devices.append(
                {
                    "vid": d["vendor_id"],
                    "pid": d["product_id"],
                    "path": d["path"].decode() if isinstance(d["path"], bytes) else d["path"],
                    "product": d.get("product_string", ""),
                    "manufacturer": d.get("manufacturer_string", ""),
                }
            )
        return devices

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN LOOP
    # ──────────────────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Background HID read loop."""
        period = 1.0 / max(self.config.poll_rate_hz, 1.0)
        last_heartbeat = 0.0

        # Emit session_start
        self._emit_session_start()

        while self._running:
            loop_start = time.time()

            # Read report
            report = self._read_report()
            if report is None:
                time.sleep(0.001)
                continue

            self._reports_read += 1

            # Decode state
            state = self._decode_report(report)
            state.host_ts_ns = clock_ns()

            # Process and emit events
            self._process_state(state)

            # Heartbeat
            now = time.time()
            if now - last_heartbeat >= 5.0:
                self._emit_heartbeat(now)
                last_heartbeat = now

            # Pace
            elapsed = time.time() - loop_start
            sleep_time = period - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Session end
        self._emit_session_end()

    # ──────────────────────────────────────────────────────────────────────────
    # HID REPORT READING
    # ──────────────────────────────────────────────────────────────────────────

    def _read_report(self) -> bytes | None:
        """Read single input report from device."""
        if not self._device:
            return None
        try:
            # hidapi read returns list of ints or bytes
            data = self._device.read(INPUT_REPORT_SIZE, timeout_ms=10)
            if not data:
                return None
            return bytes(data)
        except Exception as e:
            log.warning(f"HID read error: {e}")
            return None

    def _decode_report(self, report: bytes) -> ControllerState:
        """Decode DualSense/DualSense Edge input report."""
        state = ControllerState()
        state.device_ts = int(time.time() * 1_000_000)  # microseconds since epoch

        if len(report) < 8:
            return state

        # Standard DualSense report layout (64 bytes)
        # Byte 0: Report ID (0x01)
        # Buttons in bytes 1-2 (16 bits)
        buttons_low = report[1] if len(report) > 1 else 0
        buttons_high = report[2] if len(report) > 2 else 0
        state.buttons = buttons_low | (buttons_high << 8)

        # Triggers
        state.l2 = report[3] if len(report) > 3 else 0
        state.r2 = report[4] if len(report) > 4 else 0

        # Sticks (left: 5-6, right: 7-8)
        state.lx = report[5] if len(report) > 5 else 128
        state.ly = report[6] if len(report) > 6 else 128
        state.rx = report[7] if len(report) > 7 else 128
        state.ry = report[8] if len(report) > 8 else 128

        # IMU data (if present in extended report)
        # Gyro: bytes 13-18 (3x int16)
        # Accel: bytes 19-24 (3x int16)
        if len(report) >= 25:
            import struct

            state.gyro_x = struct.unpack_from("<h", report, 13)[0]
            state.gyro_y = struct.unpack_from("<h", report, 15)[0]
            state.gyro_z = struct.unpack_from("<h", report, 17)[0]
            state.accel_x = struct.unpack_from("<h", report, 19)[0]
            state.accel_y = struct.unpack_from("<h", report, 21)[0]
            state.accel_z = struct.unpack_from("<h", report, 23)[0]

        # Battery (byte 30)
        if len(report) > 30:
            state.battery = report[30]

        # USB state (byte 31)
        if len(report) > 31:
            state.usb_state = report[31]

        return state

    # ──────────────────────────────────────────────────────────────────────────
    # STATE PROCESSING & EVENT EMISSION
    # ──────────────────────────────────────────────────────────────────────────

    def _process_state(self, state: ControllerState) -> None:
        """Compare with previous state, emit events, update buffer."""
        now_ns = state.host_ts_ns

        # Button changes
        changed = state.buttons ^ self._prev_state.buttons
        if changed:
            pressed = changed & state.buttons
            released = changed & ~state.buttons
            self._emit_button_events(pressed, released, now_ns)

        # Trigger onsets (edge detection)
        self._check_trigger_onsets(state, now_ns)

        # Stick motion (deadzone)
        self._check_stick_motion(state, now_ns)

        # IMU tremor sample (if IMU available)
        if any(
            [state.gyro_x, state.gyro_y, state.gyro_z, state.accel_x, state.accel_y, state.accel_z]
        ):
            self._emit_tremor_sample(state, now_ns)

        # Generic controller event (full state dump at lower rate)
        if self._reports_read % 10 == 0:  # ~100Hz if poll=1000Hz
            self._emit_controller_event(state, now_ns)

        # Update rolling buffer
        self._add_to_buffer(
            now_ns,
            SourceLobe.CONTROLLER,
            EventType.CONTROLLER_EVENT,
            {
                "buttons": state.buttons,
                "l2": state.l2,
                "r2": state.r2,
                "lx": state.lx,
                "ly": state.ly,
                "rx": state.rx,
                "ry": state.ry,
            },
        )

        # Update touch file for presence sync (on any input)
        if changed or state.l2 > self._trigger_threshold or state.r2 > self._trigger_threshold:
            self._touch_presence()

        self._prev_state = state

    def _check_trigger_onsets(self, state: ControllerState, now_ns: int) -> None:
        """Detect trigger press onsets (rising edge past threshold)."""
        # L2
        if self._prev_l2 <= self._trigger_threshold and state.l2 > self._trigger_threshold:
            causal_parent = self.find_causal_parent()
            self.bus.emit_raw(
                source_lobe=SourceLobe.CONTROLLER,
                event_type="trigger_onset",
                payload={
                    "trigger": "L2",
                    "amplitude": state.l2 / 255.0,
                    "device_ts_ms": state.device_ts // 1000,
                    "causal_parent_ns": causal_parent,
                },
                clock_ns_override=now_ns,
                session_head_ns=self.session_head_ns,
            )
        # R2
        if self._prev_r2 <= self._trigger_threshold and state.r2 > self._trigger_threshold:
            causal_parent = self.find_causal_parent()
            self.bus.emit_raw(
                source_lobe=SourceLobe.CONTROLLER,
                event_type="trigger_onset",
                payload={
                    "trigger": "R2",
                    "amplitude": state.r2 / 255.0,
                    "device_ts_ms": state.device_ts // 1000,
                    "causal_parent_ns": causal_parent,
                },
                clock_ns_override=now_ns,
                session_head_ns=self.session_head_ns,
            )

        self._prev_l2 = state.l2
        self._prev_r2 = state.r2

    def _check_stick_motion(self, state: ControllerState, now_ns: int) -> None:
        """Detect significant stick motion (beyond deadzone)."""
        deadzone = 15
        for stick, x, y, px, py in [
            ("left", state.lx, state.ly, self._prev_state.lx, self._prev_state.ly),
            ("right", state.rx, state.ry, self._prev_state.rx, self._prev_state.ry),
        ]:
            dx = abs(x - 128)
            dy = abs(y - 128)
            if dx > deadzone or dy > deadzone:
                # Significant motion from center
                causal_parent = self.find_causal_parent()
                self.bus.emit_raw(
                    source_lobe=SourceLobe.CONTROLLER,
                    event_type="stick_motion",
                    payload={
                        "stick": stick,
                        "x": (x - 128) / 127.0,  # Normalized -1..1
                        "y": (y - 128) / 127.0,
                        "dx": (x - px) / 127.0,
                        "dy": (y - py) / 127.0,
                        "causal_parent_ns": causal_parent,
                    },
                    clock_ns_override=now_ns,
                    session_head_ns=self.session_head_ns,
                )

    def _emit_tremor_sample(self, state: ControllerState, now_ns: int) -> None:
        """Emit IMU tremor sample for biometric correlation."""
        causal_parent = self.find_causal_parent()
        self.bus.emit_raw(
            source_lobe=SourceLobe.CONTROLLER,
            event_type="tremor_sample",
            payload={
                "gyro": [state.gyro_x, state.gyro_y, state.gyro_z],
                "accel": [state.accel_x, state.accel_y, state.accel_z],
                "causal_parent_ns": causal_parent,
            },
            clock_ns_override=now_ns,
            session_head_ns=self.session_head_ns,
        )

    def _emit_button_events(self, pressed: int, released: int, now_ns: int) -> None:
        """Emit button press/release events."""
        for name, mask in [
            ("cross", Buttons.CROSS),
            ("circle", Buttons.CIRCLE),
            ("square", Buttons.SQUARE),
            ("triangle", Buttons.TRIANGLE),
            ("l1", Buttons.L1),
            ("r1", Buttons.R1),
            ("l2_btn", Buttons.L2),
            ("r2_btn", Buttons.R2),
            ("create", Buttons.CREATE),
            ("options", Buttons.OPTIONS),
            ("l3", Buttons.L3),
            ("r3", Buttons.R3),
            ("ps", Buttons.PS),
            ("touchpad", Buttons.TOUCHPAD),
            ("mute", Buttons.MUTE),
            ("fn_left", Buttons.FN_LEFT),
            ("fn_right", Buttons.FN_RIGHT),
        ]:
            if pressed & mask:
                causal_parent = self.find_causal_parent()
                self.bus.emit_raw(
                    source_lobe=SourceLobe.CONTROLLER,
                    event_type="controller_event",
                    payload={
                        "button": name,
                        "value": 1.0,
                        "action": "press",
                        "causal_parent_ns": causal_parent,
                    },
                    clock_ns_override=now_ns,
                    session_head_ns=self.session_head_ns,
                )
            elif released & mask:
                causal_parent = self.find_causal_parent()
                self.bus.emit_raw(
                    source_lobe=SourceLobe.CONTROLLER,
                    event_type="controller_event",
                    payload={
                        "button": name,
                        "value": 0.0,
                        "action": "release",
                        "causal_parent_ns": causal_parent,
                    },
                    clock_ns_override=now_ns,
                    session_head_ns=self.session_head_ns,
                )

    def _emit_controller_event(self, state: ControllerState, now_ns: int) -> None:
        """Emit periodic full state snapshot."""
        causal_parent = self.find_causal_parent()
        self.bus.emit_raw(
            source_lobe=SourceLobe.CONTROLLER,
            event_type="controller_event",
            payload={
                "buttons": state.buttons,
                "l2": state.l2 / 255.0,
                "r2": state.r2 / 255.0,
                "lx": (state.lx - 128) / 127.0,
                "ly": (state.ly - 128) / 127.0,
                "rx": (state.rx - 128) / 127.0,
                "ry": (state.ry - 128) / 127.0,
                "battery": state.battery,
                "usb_state": state.usb_state,
                "causal_parent_ns": causal_parent,
            },
            clock_ns_override=now_ns,
            session_head_ns=self.session_head_ns,
        )

        # Call presence callback for fusion engine
        if self._presence_callback:
            try:
                self._presence_callback(
                    {
                        "lobe": "controller",
                        "causal_density": self._causal_density,
                        "last_trigger": self._last_trigger_value,
                        "last_event_ns": self._last_event_ns,
                    }
                )
            except Exception:
                pass

    def _emit_session_start(self) -> None:
        self.bus.emit_raw(
            source_lobe=SourceLobe.CONTROLLER,
            event_type="session_start",
            payload={
                "device_path": self._device_path,
                "poll_rate_hz": self.config.poll_rate_hz,
                "buffer_size": self.config.buffer_size,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    def _emit_heartbeat(self, now: float) -> None:
        self.bus.emit_raw(
            source_lobe=SourceLobe.CONTROLLER,
            event_type="heartbeat",
            payload={
                "uptime_s": round(now - self._start_time, 1),
                "reports_read": self._reports_read,
                "buffer_fill": len(self._buffer),
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    def _emit_session_end(self) -> None:
        elapsed = max(time.time() - self._start_time, 1e-6)
        self.bus.emit_raw(
            source_lobe=SourceLobe.CONTROLLER,
            event_type="session_end",
            payload={
                "reports_read": self._reports_read,
                "events_emitted": self.bus.events_emitted,
                "elapsed_s": round(elapsed, 2),
                "avg_rate": round(self._reports_read / elapsed, 1),
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # PRESENCE TOUCH FILE
    # ──────────────────────────────────────────────────────────────────────────

    def _touch_presence(self) -> None:
        """Update touch file mtime for streamer presence sync."""
        try:
            self.presence_touch_file.touch(exist_ok=True)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────────
    # BUFFER MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────

    def _add_to_buffer(
        self, clock_ns: int, source_lobe: SourceLobe, event_type: EventType, payload: dict
    ) -> None:
        """Add entry to rolling causal buffer."""
        entry = BufferEntry(
            clock_ns=clock_ns,
            source_lobe=source_lobe,
            event_type=event_type,
            payload=payload,
            causal_parent_ns=self.find_causal_parent(),
        )
        self._buffer.append(entry)


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: List available controllers
# ──────────────────────────────────────────────────────────────────────────────


def list_controllers() -> list[dict]:
    """List all HID devices that look like controllers."""
    result = []
    for d in hid.enumerate():
        vid = d["vendor_id"]
        pid = d["product_id"]
        # Common controller VIDs
        if vid in (0x054C, 0x045E, 0x057E, 0x2DC8, 0x0F0D):  # Sony, MS, Nintendo, Razer, Hori
            result.append(
                {
                    "vid": vid,
                    "pid": pid,
                    "path": d["path"].decode() if isinstance(d["path"], bytes) else d["path"],
                    "product": d.get("product_string", ""),
                    "manufacturer": d.get("manufacturer_string", ""),
                }
            )
    return result
