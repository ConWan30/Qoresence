"""Private haptic probe — enqueue only, default OFF.

Enable with ``QORESENCE_HAPTIC_PROBE=1`` or ``--haptic-probe``.
Logs land under ``logs/haptic/<session>_<stamp>.jsonl`` (session-scoped).

Deliberately *not* exposed: CIVIF ticks, Session Theater, NarrativeEngine,
MCP ``tools/list``, clip identifiers, score digits, HID button names,
``controller_bodied``. Same observation class as CerLog / OTel Rule 5:
the HID/IMU caller must only enqueue.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qoresence.sync.haptic_echo import EchoDetector, HapticPulse, RumbleTracker
from qoresence.sync.haptic_output import parse_output_rumble
from qoresence.sync.haptic_schema import (
    HAPTIC_PLANE,
    HAPTIC_SCHEMA,
    SOURCE_LOBE,
    empty_record,
    licenses_fail_closed,
)

log = logging.getLogger(__name__)

DEFAULT_DIR = Path("logs/haptic")
_TRUE = {"1", "true", "yes", "on"}


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_HAPTIC_PROBE", "0").strip().lower() in _TRUE


def _session_id() -> str:
    try:
        from qoresence.core.session import SessionAuthority

        ident = SessionAuthority.current()
        if ident is not None:
            return str(ident.session_id or "")
    except Exception:
        pass
    return os.getenv("QORESENCE_SESSION_ID") or ""


def _in_ivc_window(t_start_ns: int, coup: dict[str, Any]) -> tuple[bool, float | None, int | None]:
    video = int(coup.get("video_clock_ns") or 0)
    if video <= 0:
        return False, None, None
    band = coup.get("lag_band_ms") or [0.0, 120.0]
    try:
        hi_ms = float(band[1]) if len(band) > 1 else 120.0
    except Exception:
        hi_ms = 120.0
    try:
        lead_ms = float(coup.get("lead_ms") or 24.0)
    except Exception:
        lead_ms = 24.0
    lo_ns = video - int(hi_ms * 1e6)
    hi_ns = video + int(lead_ms * 1e6)
    dt_ms = (int(t_start_ns) - video) / 1e6
    return lo_ns <= int(t_start_ns) <= hi_ns, round(dt_ms, 3), video


def pulse_to_record(
    pulse: HapticPulse,
    *,
    session_id: str,
    ivc: dict[str, Any] | None,
) -> dict[str, Any]:
    coup = dict(ivc or {})
    in_win, dt_ms, video = _in_ivc_window(pulse.t_start_ns, coup)
    coupled = bool(pulse.hid_present)
    reason = (
        "imu_echo_sustain" if pulse.channel == "imu_echo" else "hid_output_rumble"
    )
    mode = pulse.transport if pulse.transport in {"usb", "bt"} else (pulse.transport or "unknown")
    if mode not in {"usb", "bt", "unknown", "none"}:
        mode = "unknown"
    rec: dict[str, Any] = {
        "schema_version": HAPTIC_SCHEMA,
        "plane": HAPTIC_PLANE,
        "session_id": str(session_id or ""),
        "clock_ns": int(pulse.t_start_ns),
        "source_lobe": SOURCE_LOBE,
        "kind": "haptic_transient",
        "t_start_ns": int(pulse.t_start_ns),
        "t_end_ns": int(pulse.t_end_ns),
        "duration_ms": round(pulse.duration_ms, 3),
        "intensity": pulse.intensity,
        "intensity_01": round(float(pulse.intensity_01), 3),
        "channel": pulse.channel,
        "actuators": list(pulse.actuators),
        "coupled": coupled,
        "signature": pulse.signature,
        "qualification": "observed",
        "licenses": licenses_fail_closed(observed=True, coupled=coupled),
        "provenance": {
            "connection_mode": mode,
            "reason": reason,
            "coupling_reason": "hid_reports_this_host" if coupled else "unattributed",
            "video_clock_ns": video,
            "frame_seq": coup.get("frame_seq"),
            "ivc_dt_ms": dt_ms,
            "in_ivc_window": in_win,
            "coupling": coup.get("coupling"),
        },
    }
    return rec


class HapticProbe:
    """Background observer. Hot path: ``put_nowait`` only."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        session_id: str = "",
        jsonl_path: Path | None = None,
        queue_size: int = 1024,
        ivc_lookup: Callable[[], dict[str, Any]] | None = None,
        stall_worker: bool = False,
        maxlen: int = 256,
    ) -> None:
        self.enabled = bool(enabled)
        self.session_id = str(session_id or "")
        self._jsonl = Path(jsonl_path) if jsonl_path is not None else None
        self._ivc_lookup = ivc_lookup
        self._q: queue.Queue[tuple[Any, ...] | None] = queue.Queue(maxsize=max(8, int(queue_size)))
        self._ring: deque[dict[str, Any]] = deque(maxlen=max(16, int(maxlen)))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._busy = 0
        self._dropped = 0
        self._echo = EchoDetector()
        self._rumble = RumbleTracker()
        self._worker: threading.Thread | None = None
        if not self.enabled:
            return
        self._worker = threading.Thread(
            target=self._run,
            name="qoresence-haptic-probe",
            daemon=True,
            kwargs={"stall": bool(stall_worker)},
        )
        self._worker.start()

    def observe_imu(
        self,
        *,
        clock_ns: int,
        accel: tuple[int, int, int],
        gyro: tuple[int, int, int] = (0, 0, 0),
        analog_slew: float = 0.0,
        transport: str = "unknown",
        hid_present: bool = False,
    ) -> None:
        if not self.enabled:
            return
        self._enqueue(
            (
                "imu",
                int(clock_ns),
                tuple(int(x) for x in accel),
                tuple(int(x) for x in gyro),
                float(analog_slew),
                str(transport or "unknown"),
                bool(hid_present),
            )
        )

    def observe_output_report(
        self,
        raw: bytes,
        *,
        clock_ns: int,
        hid_present: bool = False,
        transport: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        parsed = parse_output_rumble(raw)
        if parsed is None:
            return
        self._enqueue(
            (
                "rumble",
                int(clock_ns),
                int(parsed["rumble_left"]),
                int(parsed["rumble_right"]),
                str(transport or parsed.get("transport") or "unknown"),
                bool(hid_present),
            )
        )

    def record_unavailable(
        self,
        *,
        clock_ns: int = 0,
        reason: str = "channel_unavailable",
        connection_mode: str = "none",
    ) -> dict[str, Any]:
        rec = empty_record(
            session_id=self.session_id or _session_id(),
            clock_ns=int(clock_ns or 0),
            reason=reason,
            connection_mode=connection_mode,
        )
        with self._lock:
            self._ring.append(rec)
        if self.enabled:
            self._enqueue(("jsonl", rec))
        return rec

    def recent(self, n: int = 40) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._ring)
        return rows[-max(1, min(200, int(n))) :]

    def flush(self, timeout_s: float = 2.0) -> None:
        deadline = time.monotonic() + max(0.05, float(timeout_s))
        while time.monotonic() < deadline:
            if self._q.empty() and self._busy == 0:
                time.sleep(0.02)
                if self._q.empty() and self._busy == 0:
                    return
            time.sleep(0.01)

    def stop(self) -> None:
        if not self.enabled:
            return
        self._stop.set()
        try:
            self._q.put_nowait(None)
        except queue.Full:
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(None)
            except queue.Full:
                pass
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None
        self.enabled = False

    def _enqueue(self, item: tuple[Any, ...]) -> None:
        try:
            self._q.put_nowait(item)
            return
        except queue.Full:
            pass
        try:
            self._q.get_nowait()
            self._dropped += 1
        except queue.Empty:
            pass
        try:
            self._q.put_nowait(item)
        except queue.Full:
            self._dropped += 1

    def _lookup_ivc(self) -> dict[str, Any]:
        fn = self._ivc_lookup
        if fn is not None:
            try:
                return dict(fn() or {})
            except Exception:
                return {}
        try:
            from qoresence.sync.ivc import get_last_coupling

            return dict(get_last_coupling() or {})
        except Exception:
            return {}

    def _accept_pulse(self, pulse: HapticPulse | None) -> None:
        if pulse is None:
            return
        rec = pulse_to_record(
            pulse,
            session_id=self.session_id or _session_id(),
            ivc=self._lookup_ivc(),
        )
        with self._lock:
            self._ring.append(rec)
        self._write_jsonl(rec)

    def _write_jsonl(self, rec: dict[str, Any]) -> None:
        path = self._jsonl
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
        except Exception as e:
            log.debug("haptic jsonl: %s", e)

    def _run(self, stall: bool = False) -> None:
        if stall:
            self._stop.wait()
            return
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.05)
            except queue.Empty:
                continue
            if item is None:
                return
            self._busy = 1
            try:
                self._handle(item)
            except Exception as e:
                log.debug("haptic worker: %s", e)
            finally:
                self._busy = 0

    def _handle(self, item: tuple[Any, ...]) -> None:
        kind = item[0]
        if kind == "jsonl":
            rec = item[1]
            if isinstance(rec, dict):
                self._write_jsonl(rec)
            return
        if kind == "imu":
            _, clock_ns, accel, gyro, analog_slew, transport, hid_present = item
            pulse = self._echo.feed(
                clock_ns=int(clock_ns),
                accel=tuple(accel),  # type: ignore[arg-type]
                gyro=tuple(gyro),  # type: ignore[arg-type]
                analog_slew=float(analog_slew),
                transport=str(transport),
                hid_present=bool(hid_present),
            )
            self._accept_pulse(pulse)
            return
        if kind == "rumble":
            _, clock_ns, left, right, transport, hid_present = item
            pulse = self._rumble.feed(
                clock_ns=int(clock_ns),
                rumble_left=int(left),
                rumble_right=int(right),
                transport=str(transport),
                hid_present=bool(hid_present),
            )
            self._accept_pulse(pulse)


_probe: HapticProbe | None = None
_probe_lock = threading.Lock()


def reset_haptic_probe() -> None:
    global _probe
    with _probe_lock:
        p = _probe
        _probe = None
    if p is not None:
        try:
            p.stop()
        except Exception:
            pass


def start_haptic_probe(
    *,
    session_id: str = "",
    out_dir: Path | str | None = None,
    config: Any = None,
    probe: HapticProbe | None = None,
    jsonl_path: Path | None = None,
) -> HapticProbe | None:
    """Start the process-wide probe. No-op when disabled (default)."""
    global _probe
    if probe is not None:
        with _probe_lock:
            _probe = probe
        return probe
    enabled = bool(getattr(config, "enabled", False)) or _env_enabled()
    if not enabled:
        return None
    sid = session_id or _session_id()
    path = jsonl_path
    if path is None:
        root = Path(out_dir) if out_dir is not None else Path(
            getattr(config, "out_dir", None) or DEFAULT_DIR
        )
        try:
            root.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (sid or "session"))[:48]
        path = root / f"{safe}_{stamp}.jsonl"
    qsize = int(getattr(config, "queue_size", 1024) or 1024)
    started = HapticProbe(enabled=True, session_id=sid, jsonl_path=path, queue_size=qsize)
    with _probe_lock:
        old = _probe
        _probe = started
    if old is not None and old is not started:
        try:
            old.stop()
        except Exception:
            pass
    log.info("haptic probe enabled (private JSONL %s) — observation only", path)
    return started


def stop_haptic_probe() -> None:
    reset_haptic_probe()


def get_haptic_probe() -> HapticProbe | None:
    return _probe


def observe_imu(
    *,
    clock_ns: int,
    accel: tuple[int, int, int],
    gyro: tuple[int, int, int] = (0, 0, 0),
    analog_slew: float = 0.0,
    transport: str = "unknown",
    hid_present: bool = False,
) -> None:
    p = _probe
    if p is None or not p.enabled:
        return
    p.observe_imu(
        clock_ns=clock_ns,
        accel=accel,
        gyro=gyro,
        analog_slew=analog_slew,
        transport=transport,
        hid_present=hid_present,
    )


def recent_records(n: int = 40) -> list[dict[str, Any]]:
    p = _probe
    if p is None:
        return []
    return p.recent(n)
