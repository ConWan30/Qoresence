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

# Sony DualSense / DualSense Edge
DS_EDGE_VID = 0x054C  # Sony
DS_EDGE_PID = 0x0DF2  # DualSense Edge Wireless Controller
DS_PID = 0x0CE6  # DualSense (standard)
# Try these in order when config has no explicit VID/PID
_SONY_CONTROLLER_PIDS = (0x0DF2, 0x0CE6, 0x05C4)  # Edge, DualSense, DS4

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
        self._connected = False
        self._reconnects = 0
        self._reconnect_s = 1.5
        self._last_transport: str | None = None
        self._ever_connected = False

        # State
        self._running = False
        self._thread: threading.Thread | None = None
        self._prev_state = ControllerState()

        # Rolling buffer for causal correlation
        self._buffer = deque(maxlen=config.buffer_size)

        # Trigger onset detection — debounce requires N consecutive readings
        # above threshold to reject noise-induced phantom onsets
        self._prev_l2 = 0
        self._prev_r2 = 0
        self._trigger_threshold = 30  # ~12% press
        self._l2_above_count = 0
        self._r2_above_count = 0
        self._trigger_debounce = 2  # consecutive readings needed

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
        # Analog hold for IVC sustain (throttled; not an edge flood)
        self._last_hold_ns = 0

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start the capture thread. Waits for DualSense if none is listed yet."""
        if self._running:
            log.warning("ControllerRuntime already running")
            return True

        opened = self._open_device(quiet=True)
        self._connected = bool(opened)
        self._ever_connected = bool(opened)
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(
            target=self._run_loop, name="qoresence-controller", daemon=True
        )
        self._thread.start()
        _register_runtime(self)

        if opened:
            log.info(
                "Controller lobe started: %s, poll_rate=%.0fHz, buffer=%s",
                self._device_path,
                self.config.poll_rate_hz,
                self.config.buffer_size,
            )
        else:
            log.info("Controller lobe waiting for DualSense (USB/BT hot-plug)")
        return True

    def stop(self) -> None:
        """Stop capture thread and close device."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self._drop_device()
        _unregister_runtime(self)
        log.info("Controller lobe stopped")

    def is_running(self) -> bool:
        return self._running

    def set_presence_callback(self, callback: callable) -> None:
        """Set callback for presence status updates (for fusion engine)."""
        self._presence_callback = callback

    def get_stats(self) -> dict:
        """Get controller statistics for health / Deck (no bus emit)."""
        return {
            "connected": bool(self._connected),
            "waiting": bool(self._running and not self._connected),
            "device": self._device_path,
            "transport": self._last_transport,
            "reports": int(self._reports_read),
            "reconnects": int(self._reconnects),
            "last_trigger": self._last_trigger_value
            if hasattr(self, "_last_trigger_value")
            else 0.0,
            "stick_motion": self._last_stick_motion if hasattr(self, "_last_stick_motion") else 0.0,
            "causal_density": self._causal_density if hasattr(self, "_causal_density") else 0,
            "last_event_ns": self._last_event_ns if hasattr(self, "_last_event_ns") else 0,
        }

    def ingest_report(self, report: bytes, *, host_ts_ns: int | None = None) -> ControllerState:
        """Decode + process one HID report (tests / software DualSense)."""
        state = self._decode_report(report)
        if host_ts_ns is not None:
            state.host_ts_ns = int(host_ts_ns)
        self._push_imu(state)
        self._process_state(state)
        self._reports_read += 1
        return state

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

    def _drop_device(self) -> None:
        """Close HID handle without emitting. Caller owns reconnect."""
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
        self._device = None
        self._connected = False

    def _open_device(self, *, quiet: bool = False) -> bool:
        """Open HID device by VID/PID or path (DualSense Edge preferred)."""
        # Priority 1: Explicit path
        if self.config.device_path:
            try:
                self._device = HIDDevice()
                path = self.config.device_path
                path_b = path.encode() if isinstance(path, str) else path
                self._device.open_path(path_b)
                self._device_path = path if isinstance(path, str) else path.decode(errors="replace")
                log.info("Controller HID opened by path: %s", self._device_path)
                return True
            except Exception as e:
                log.error("Failed to open HID path %s: %s", self.config.device_path, e)
                self._device = None
                return False

        # Priority 2: Explicit VID/PID
        if self.config.device_vid is not None and self.config.device_pid is not None:
            try:
                self._device = HIDDevice()
                vid, pid = int(self.config.device_vid), int(self.config.device_pid)
                self._device.open(vid, pid)
                self._device_path = f"vid={vid:04x},pid={pid:04x}"
                log.info("Controller HID opened: %s", self._device_path)
                return True
            except Exception as e:
                log.error(
                    "Failed to open HID vid=%s pid=%s: %s",
                    self.config.device_vid,
                    self.config.device_pid,
                    e,
                )
                self._device = None
                return False

        # Priority 3: Enumerate Sony DualSense family and open first usable path
        candidates = list_controllers()
        sony = [c for c in candidates if int(c.get("vid") or 0) == DS_EDGE_VID]

        # Prefer Edge product string / Edge PID, then any Sony pad
        def _rank(c: dict) -> int:
            pid = int(c.get("pid") or 0)
            prod = (c.get("product") or "").lower()
            if "edge" in prod or pid == DS_EDGE_PID:
                return 0
            if pid in _SONY_CONTROLLER_PIDS:
                return 1
            return 2

        sony.sort(key=_rank)
        last_err: Exception | None = None
        for c in sony:
            path = c.get("path")
            if not path:
                continue
            try:
                self._device = HIDDevice()
                path_b = path.encode() if isinstance(path, str) else path
                self._device.open_path(path_b)
                self._device_path = (
                    f"{c.get('product') or 'Sony'} vid={int(c.get('vid') or 0):04x},"
                    f"pid={int(c.get('pid') or 0):04x}"
                )
                log.info("Controller HID opened: %s", self._device_path)
                return True
            except Exception as e:
                last_err = e
                self._device = None
                continue

        # Priority 4: Classic open by known PIDs
        for pid in _SONY_CONTROLLER_PIDS:
            try:
                self._device = HIDDevice()
                self._device.open(DS_EDGE_VID, pid)
                self._device_path = f"vid={DS_EDGE_VID:04x},pid={pid:04x}"
                log.info("Controller HID opened: %s", self._device_path)
                return True
            except Exception as e:
                last_err = e
                self._device = None
                continue

        listed = [
            f"vid={c.get('vid'):04x} pid={c.get('pid'):04x} {c.get('product')}"
            for c in candidates[:8]
        ]
        msg = f"DualSense HID not open (Edge/standard). last_err={last_err} listed={listed}"
        if quiet:
            log.debug(msg)
        else:
            log.warning(msg)
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
        """Background HID read loop. Re-opens the pad after unplug / late plug-in."""
        period = 1.0 / max(self.config.poll_rate_hz, 1.0)
        last_heartbeat = 0.0
        last_retry = 0.0
        emitted_start = False

        if self._connected:
            self._emit_session_start()
            emitted_start = True

        while self._running:
            loop_start = time.time()

            if not self._connected:
                now = time.time()
                if now - last_retry >= self._reconnect_s:
                    last_retry = now
                    if self._open_device(quiet=True):
                        self._connected = True
                        self._ever_connected = True
                        self._reconnects += 1
                        self._prev_state = ControllerState()
                        log.info("DualSense hot-plug: %s", self._device_path)
                        if not emitted_start:
                            self._emit_session_start()
                            emitted_start = True
                time.sleep(min(0.05, self._reconnect_s))
                continue

            report = self._read_report()
            if report is None:
                time.sleep(0.001)
                continue

            self._reports_read += 1

            state = self._decode_report(report)
            state.host_ts_ns = clock_ns()

            # IMU ring first so a press in this report can see the precursor.
            self._push_imu(state)
            self._process_state(state)

            now = time.time()
            if now - last_heartbeat >= 5.0:
                self._emit_heartbeat(now)
                last_heartbeat = now

            elapsed = time.time() - loop_start
            sleep_time = period - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        if self._ever_connected:
            self._emit_session_end()

    # ──────────────────────────────────────────────────────────────────────────
    # HID REPORT READING
    # ──────────────────────────────────────────────────────────────────────────

    def _read_report(self) -> bytes | None:
        """Read single input report from device (USB 64 or BT 78)."""
        if not self._device:
            return None
        try:
            data = self._device.read(78, timeout_ms=8)
            if not data:
                return None
            return bytes(data)
        except Exception as e:
            log.warning("HID read error: %s — will retry open", e)
            self._drop_device()
            return None

    def _decode_report(self, report: bytes) -> ControllerState:
        """Decode DualSense / Edge via the QorTroller-forked USB/BT map."""
        from qoresence.sync.hid_report import parse_report

        state = ControllerState()
        state.device_ts = int(time.time() * 1_000_000)
        state.host_ts_ns = clock_ns()
        if len(report) < 8:
            return state
        parsed = parse_report(report)
        self._last_transport = str(parsed.get("transport") or "") or None
        state.buttons = int(parsed["buttons"])
        state.l2 = int(parsed["l2"])
        state.r2 = int(parsed["r2"])
        stick_dz = 8
        lx, ly, rx, ry = int(parsed["lx"]), int(parsed["ly"]), int(parsed["rx"]), int(parsed["ry"])
        state.lx = 128 if abs(lx - 128) <= stick_dz else lx
        state.ly = 128 if abs(ly - 128) <= stick_dz else ly
        state.rx = 128 if abs(rx - 128) <= stick_dz else rx
        state.ry = 128 if abs(ry - 128) <= stick_dz else ry
        state.gyro_x = int(parsed["gyro_x"])
        state.gyro_y = int(parsed["gyro_y"])
        state.gyro_z = int(parsed["gyro_z"])
        state.accel_x = int(parsed["accel_x"])
        state.accel_y = int(parsed["accel_y"])
        state.accel_z = int(parsed["accel_z"])
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

        self._push_hold(state, now_ns)
        self._prev_state = state

    def _latest_frame_seq(self) -> int | None:
        try:
            from qoresence.monitor.frame_hub import get_latest_stamp

            st = get_latest_stamp()
            if st.get("has_frame"):
                return int(st.get("seq") or 0) or None
        except Exception:
            return None
        return None

    def _push_imu(self, state: ControllerState) -> None:
        try:
            from qoresence.sync.imu_ring import push_imu

            push_imu(
                clock_ns=state.host_ts_ns,
                gyro=(state.gyro_x, state.gyro_y, state.gyro_z),
                accel=(state.accel_x, state.accel_y, state.accel_z),
                frame_seq=self._latest_frame_seq(),
            )
        except Exception:
            pass

    def _push_hold(self, state: ControllerState, now_ns: int) -> None:
        """Throttled analog snapshot so IVC couples sprint/steer holds."""
        if now_ns - int(self._last_hold_ns or 0) < 16_000_000:
            return
        self._last_hold_ns = now_ns
        try:
            from qoresence.sync.input_ring import set_hold as _set_hold

            stick_floor = 20  # same deadzone as _check_stick_motion

            def _mag(x: int, y: int) -> float:
                m = max(abs(int(x) - 128), abs(int(y) - 128))
                if m <= stick_floor:
                    return 0.0
                return min(1.0, m / 127.0)

            r2 = (state.r2 / 255.0) if state.r2 > self._trigger_threshold else 0.0
            l2 = (state.l2 / 255.0) if state.l2 > self._trigger_threshold else 0.0
            _set_hold(
                clock_ns=now_ns,
                r2=r2,
                l2=l2,
                left=_mag(state.lx, state.ly),
                right=_mag(state.rx, state.ry),
            )
        except Exception:
            pass

    def _push_input_ring(
        self,
        *,
        kind: str,
        name: str,
        value: float,
        clock_ns: int,
        buttons_mask: int | None = None,
    ) -> None:
        """Best-effort InputRing edge for IVC / clip sidecar (additive)."""
        try:
            from qoresence.sync.event_bind import HidOnset, get_event_binder
            from qoresence.sync.imu_ring import get_imu_ring
            from qoresence.sync.input_ring import push as _ring_push

            frame_seq = self._latest_frame_seq()
            precursor = None
            if kind in {"press", "trigger"}:
                try:
                    precursor = get_imu_ring().precursor_ms(clock_ns)
                except Exception:
                    precursor = None
            _ring_push(
                {
                    "clock_ns": clock_ns,
                    "kind": kind,
                    "name": name,
                    "value": value,
                    "buttons_mask": buttons_mask,
                    "frame_seq": frame_seq,
                    "imu_precursor_ms": precursor,
                }
            )
            if kind in {"press", "trigger"}:
                get_event_binder().push_hid(
                    HidOnset(
                        clock_ns=clock_ns,
                        name=name,
                        kind=kind,
                        frame_seq=frame_seq,
                        imu_precursor_ms=precursor,
                    )
                )
        except Exception:
            pass

    def _check_trigger_onsets(self, state: ControllerState, now_ns: int) -> None:
        """Detect trigger press onsets (rising edge past threshold).

        Uses a debounce counter to require N consecutive readings above
        threshold before firing — rejects noise-induced phantom onsets.
        The onset fires when the debounce count reaches the threshold,
        replacing the simple prev <= threshold check.
        """
        # L2 — debounce: count consecutive readings above threshold
        if state.l2 > self._trigger_threshold:
            self._l2_above_count += 1
        else:
            self._l2_above_count = 0
        # Fire when debounce count hits the threshold (first time only)
        if self._l2_above_count == self._trigger_debounce:
            causal_parent = self.find_causal_parent()
            amp = state.l2 / 255.0
            self.bus.emit_raw(
                source_lobe=SourceLobe.CONTROLLER,
                event_type="trigger_onset",
                payload={
                    "trigger": "L2",
                    "amplitude": amp,
                    "device_ts_ms": state.device_ts // 1000,
                    "causal_parent_ns": causal_parent,
                },
                clock_ns_override=now_ns,
                session_head_ns=self.session_head_ns,
            )
            self._push_input_ring(kind="trigger", name="L2", value=amp, clock_ns=now_ns)
        # R2 — debounce: count consecutive readings above threshold
        if state.r2 > self._trigger_threshold:
            self._r2_above_count += 1
        else:
            self._r2_above_count = 0
        # Fire when debounce count hits the threshold (first time only)
        if self._r2_above_count == self._trigger_debounce:
            causal_parent = self.find_causal_parent()
            amp = state.r2 / 255.0
            self.bus.emit_raw(
                source_lobe=SourceLobe.CONTROLLER,
                event_type="trigger_onset",
                payload={
                    "trigger": "R2",
                    "amplitude": amp,
                    "device_ts_ms": state.device_ts // 1000,
                    "causal_parent_ns": causal_parent,
                },
                clock_ns_override=now_ns,
                session_head_ns=self.session_head_ns,
            )
            self._push_input_ring(kind="trigger", name="R2", value=amp, clock_ns=now_ns)

        self._prev_l2 = state.l2
        self._prev_r2 = state.r2

    def _check_stick_motion(self, state: ControllerState, now_ns: int) -> None:
        """Detect significant stick motion (beyond deadzone).

        Bus emit keeps prior behavior; InputRing only gets *edges* (enter
        deadzone-out) so IVC is not flooded at poll rate.
        """
        deadzone = 20  # raw units around center 128 — tuned to reduce phantom edges
        for stick, x, y, px, py in [
            ("left", state.lx, state.ly, self._prev_state.lx, self._prev_state.ly),
            ("right", state.rx, state.ry, self._prev_state.rx, self._prev_state.ry),
        ]:
            dx = abs(x - 128)
            dy = abs(y - 128)
            pdx = abs(px - 128)
            pdy = abs(py - 128)
            outside = dx > deadzone or dy > deadzone
            was_outside = pdx > deadzone or pdy > deadzone
            if outside:
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
                # InputRing: edge only (center → outside)
                if not was_outside:
                    mag = min(1.0, max(dx, dy) / 127.0)
                    self._push_input_ring(kind="stick", name=stick, value=mag, clock_ns=now_ns)

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
                self._push_input_ring(
                    kind="press",
                    name=name,
                    value=1.0,
                    clock_ns=now_ns,
                    buttons_mask=int(pressed) if pressed else None,
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
                self._push_input_ring(kind="release", name=name, value=0.0, clock_ns=now_ns)

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


_active: ControllerRuntime | None = None
_active_lock = threading.Lock()


def _register_runtime(runtime: ControllerRuntime) -> None:
    global _active
    with _active_lock:
        _active = runtime


def _unregister_runtime(runtime: ControllerRuntime) -> None:
    global _active
    with _active_lock:
        if _active is runtime:
            _active = None


def get_controller_runtime() -> ControllerRuntime | None:
    """Process-local controller lobe (None if not started)."""
    return _active


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
