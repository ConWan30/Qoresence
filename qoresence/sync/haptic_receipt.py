"""Three-rail haptic receipt — HID-in × HDMI lock × haptic-out.

Novel CIVIF clock, observation plane only. Not a rumble overlay, not a
confirmed gameplay event, and not a license to write DualSense output.

A receipt is **coupled** only when every rail licenses in the same window:

1. ``hid_in`` — this host has HID reports (pad bodied here). Empty HID
   (DualSense left on the PS5) stays dark. No button names.
2. ``hdmi_lock`` — seeing-path board license: ``board_locked`` plus a
   ConfirmTicket id. ``score_vlm_locked`` alone is a veto, never a license.
   Digits appear only when this rail licenses.
3. ``haptic_out`` — a real pulse on ``hid_output`` (USB/BT output report
   this host can parse) or ``imu_echo`` (voice-coil shake on this host).
   PS5 Bluetooth rumble on a charge-only USB cable is ``unavailable``.

``haptics_confirmed`` stays false until an operator GO. This module never
emits a bus event and never acquires a lobe lock.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from qoresence.sync.haptic_schema import HAPTIC_PLANE, licenses_fail_closed

log = logging.getLogger(__name__)
_TRUE = {"1", "true", "yes", "on"}

RECEIPT_SCHEMA = "haptic_receipt-1"
RECEIPT_SOURCE = "haptic_receipt"
HAPTIC_OUT_CHANNELS = frozenset({"hid_output", "imu_echo"})
RAIL_NAMES = ("hid_in", "hdmi_lock", "haptic_out")


def _ticket_id(*candidates: Any) -> str:
    for raw in candidates:
        if raw is None:
            continue
        if isinstance(raw, dict):
            tid = str(raw.get("confirm_ticket_id") or raw.get("ticket_id") or "").strip()
            if tid:
                return tid
            continue
        tid = str(raw or "").strip()
        if tid:
            return tid
    return ""


def rail_hid_in(*, host_has_hid_reports: bool) -> dict[str, Any]:
    ok = bool(host_has_hid_reports)
    return {
        "licensed": ok,
        "reason": "hid_reports_this_host" if ok else "hid_empty_or_foreign_host",
    }


def rail_hdmi_lock(
    *,
    board_locked: bool = False,
    score_vlm_locked: bool = False,
    confirm_ticket_id: str = "",
) -> dict[str, Any]:
    """Seeing-path license. Flag-only lock without a ticket does not couple."""
    tid = str(confirm_ticket_id or "").strip()
    locked = bool(score_vlm_locked) or bool(board_locked)
    if tid and locked:
        return {"licensed": True, "reason": "confirm_ticket", "has_ticket": True}
    if locked and not tid:
        return {"licensed": False, "reason": "lock_without_ticket", "has_ticket": False}
    return {"licensed": False, "reason": "unlocked", "has_ticket": bool(tid)}


def rail_haptic_out(*, channel: str | None, observed: bool) -> dict[str, Any]:
    ch = str(channel or "").strip()
    known = ch in HAPTIC_OUT_CHANNELS
    ok = bool(observed) and known
    return {
        "licensed": ok,
        "channel": ch if ok else "unavailable",
        "reason": "pulse_observed" if ok else "channel_unavailable",
    }


def _digits(sit: dict[str, Any] | None, *, licensed: bool) -> dict[str, int | None]:
    if not licensed or not isinstance(sit, dict):
        return {"home": None, "away": None}

    def _num(key: str) -> int | None:
        v = sit.get(key)
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return {"home": _num("home_score"), "away": _num("away_score")}


def build_receipt(
    *,
    session_id: str = "",
    clock_ns: int = 0,
    host_has_hid_reports: bool = False,
    board_locked: bool = False,
    score_vlm_locked: bool = False,
    confirm_ticket_id: str = "",
    haptic_channel: str | None = None,
    haptic_observed: bool = False,
    situation: dict[str, Any] | None = None,
    window_ms: float = 120.0,
) -> dict[str, Any]:
    """Join the three rails. Coupled only when every rail licenses."""
    hid = rail_hid_in(host_has_hid_reports=host_has_hid_reports)
    hdmi = rail_hdmi_lock(
        board_locked=board_locked,
        score_vlm_locked=score_vlm_locked,
        confirm_ticket_id=confirm_ticket_id,
    )
    haptic = rail_haptic_out(channel=haptic_channel, observed=haptic_observed)
    rails = {"hid_in": hid, "hdmi_lock": hdmi, "haptic_out": haptic}
    coupled = all(bool(rails[name]["licensed"]) for name in RAIL_NAMES)
    observed = bool(haptic["licensed"])
    kind = "haptic_receipt" if observed else "haptic_receipt_dark"
    return {
        "schema_version": RECEIPT_SCHEMA,
        "plane": HAPTIC_PLANE,
        "session_id": str(session_id or ""),
        "clock_ns": int(clock_ns or 0),
        "source_lobe": RECEIPT_SOURCE,
        "kind": kind,
        "rails": rails,
        "coupled": coupled,
        "window_ms": float(window_ms),
        "score": _digits(situation, licensed=bool(hdmi["licensed"])),
        "licenses": licenses_fail_closed(observed=observed, coupled=coupled),
        "public_surfaces": False,
        "claim_ceiling": "three_rail_co_occurrence",
    }


def receipt_from_tick_and_obs(
    tick: dict[str, Any] | None,
    haptic_obs: dict[str, Any] | None,
    *,
    window_ms: float = 120.0,
) -> dict[str, Any]:
    """Join a CIVIF live tick with a haptic_obs-1 row. No bus emit."""
    tick = tick if isinstance(tick, dict) else {}
    obs = haptic_obs if isinstance(haptic_obs, dict) else {}
    sit = tick.get("situation_snapshot") or tick.get("situation") or {}
    if not isinstance(sit, dict):
        sit = {}
    hid_host = bool(tick.get("controller_bodied") or (tick.get("input") or {}).get("bodied"))
    if obs.get("coupled") or (obs.get("provenance") or {}).get("coupling_reason") == "hid_reports_this_host":
        hid_host = True
    kind = str(obs.get("kind") or "")
    haptic_observed = kind == "haptic_transient"
    channel = obs.get("channel") if haptic_observed else None
    clock = int(obs.get("t_start_ns") or obs.get("clock_ns") or tick.get("clock_ns") or 0)
    tid = _ticket_id(
        sit,
        tick.get("confirm_ticket_id"),
        (tick.get("coupling") or {}).get("confirm_ticket_id") if isinstance(tick.get("coupling"), dict) else "",
    )
    return build_receipt(
        session_id=str(tick.get("session_id") or obs.get("session_id") or ""),
        clock_ns=clock,
        host_has_hid_reports=hid_host,
        board_locked=bool(tick.get("board_locked") or sit.get("board_locked")),
        score_vlm_locked=bool(sit.get("score_vlm_locked") or tick.get("score_vlm_locked")),
        confirm_ticket_id=tid,
        haptic_channel=str(channel) if channel else None,
        haptic_observed=haptic_observed,
        situation=sit,
        window_ms=window_ms,
    )


def validate_receipt(rec: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if not isinstance(rec, dict):
        return ["not_a_dict"]
    if rec.get("schema_version") != RECEIPT_SCHEMA:
        errs.append("schema_version")
    if rec.get("plane") != HAPTIC_PLANE:
        errs.append("plane")
    if rec.get("source_lobe") != RECEIPT_SOURCE:
        errs.append("source_lobe")
    if rec.get("kind") not in {"haptic_receipt", "haptic_receipt_dark"}:
        errs.append("kind")
    if "controller_bodied" in rec:
        errs.append("controller_bodied_forbidden")
    if rec.get("public_surfaces"):
        errs.append("public_surfaces")
    rails = rec.get("rails")
    if not isinstance(rails, dict):
        errs.append("rails")
    else:
        for name in RAIL_NAMES:
            if name not in rails or not isinstance(rails[name], dict):
                errs.append(f"rail_{name}")
            elif "licensed" not in rails[name]:
                errs.append(f"rail_{name}_licensed")
    lic = rec.get("licenses")
    if not isinstance(lic, dict):
        errs.append("licenses")
    else:
        if lic.get("haptics_confirmed"):
            errs.append("confirmed_not_phase01")
        if lic.get("haptics_signature_known"):
            errs.append("signature_known_not_phase01")
        coupled = bool(rec.get("coupled"))
        if coupled and not (
            isinstance(rails, dict)
            and all(bool((rails.get(n) or {}).get("licensed")) for n in RAIL_NAMES)
        ):
            errs.append("coupled_without_all_rails")
        if coupled and not lic.get("haptics_coupled"):
            errs.append("coupled_license_mismatch")
    score = rec.get("score")
    hdmi_ok = bool(isinstance(rails, dict) and (rails.get("hdmi_lock") or {}).get("licensed"))
    if isinstance(score, dict) and not hdmi_ok:
        if score.get("home") is not None or score.get("away") is not None:
            errs.append("digits_without_hdmi_license")
    return errs


def _obs_in_window(tick: dict[str, Any], obs: dict[str, Any], window_ms: float) -> bool:
    t = int(tick.get("clock_ns") or 0)
    o = int(obs.get("t_start_ns") or obs.get("clock_ns") or 0)
    if t <= 0 or o <= 0:
        return True
    return abs(t - o) <= int(max(1.0, float(window_ms)) * 1e6)


def _receipt_sig(rec: dict[str, Any]) -> tuple[Any, ...]:
    rails = rec.get("rails") if isinstance(rec.get("rails"), dict) else {}
    score = rec.get("score") if isinstance(rec.get("score"), dict) else {}
    return (
        rec.get("kind"),
        rec.get("coupled"),
        (rails.get("hid_in") or {}).get("licensed"),
        (rails.get("hdmi_lock") or {}).get("licensed"),
        (rails.get("haptic_out") or {}).get("channel"),
        score.get("home"),
        score.get("away"),
    )


class HapticReceiptClock:
    """Join CIVIF ticks with haptic_obs rows. Hot path: ``put_nowait`` only.

    Same observation class as CerLog / OTel Rule 5: never emit a bus event,
    never take a lobe lock, never write disk on the caller thread.
    """

    def __init__(
        self,
        *,
        persist: bool = False,
        jsonl_path: Path | None = None,
        queue_size: int = 256,
        window_ms: float = 120.0,
        stall_worker: bool = False,
        maxlen: int = 64,
    ) -> None:
        self.persist = bool(persist)
        self.window_ms = float(window_ms)
        self._jsonl = Path(jsonl_path) if jsonl_path is not None else None
        self._q: queue.Queue[tuple[Any, ...] | None] = queue.Queue(maxsize=max(8, int(queue_size)))
        self._ring: deque[dict[str, Any]] = deque(maxlen=max(8, int(maxlen)))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._busy = 0
        self._dropped = 0
        self._last_tick: dict[str, Any] | None = None
        self._last_obs: dict[str, Any] | None = None
        self._last_sig: tuple[Any, ...] | None = None
        self._worker = threading.Thread(
            target=self._run,
            name="qoresence-haptic-receipt",
            daemon=True,
            kwargs={"stall": bool(stall_worker)},
        )
        self._worker.start()

    def note_tick(self, tick: dict[str, Any] | None) -> None:
        if not isinstance(tick, dict):
            return
        self._enqueue(("tick", tick))

    def note_obs(self, obs: dict[str, Any] | None) -> None:
        if not isinstance(obs, dict):
            return
        self._enqueue(("obs", obs))

    def recent(self, n: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._ring)
        return rows[-max(1, min(80, int(n))) :]

    def last(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._ring:
                return None
            return dict(self._ring[-1])

    def flush(self, timeout_s: float = 2.0) -> None:
        deadline = time.monotonic() + max(0.05, float(timeout_s))
        while time.monotonic() < deadline:
            if self._q.empty() and self._busy == 0:
                time.sleep(0.02)
                if self._q.empty() and self._busy == 0:
                    return
            time.sleep(0.01)

    def stop(self) -> None:
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
                log.debug("haptic receipt worker: %s", e)
            finally:
                self._busy = 0

    def _handle(self, item: tuple[Any, ...]) -> None:
        kind, payload = item[0], item[1]
        if kind == "tick" and isinstance(payload, dict):
            self._last_tick = payload
        elif kind == "obs" and isinstance(payload, dict):
            self._last_obs = payload
        else:
            return
        tick = self._last_tick
        obs = self._last_obs
        if tick is None and obs is None:
            return
        use_obs = obs if isinstance(obs, dict) else None
        if tick is not None and use_obs is not None and not _obs_in_window(tick, use_obs, self.window_ms):
            use_obs = None
        rec = receipt_from_tick_and_obs(tick, use_obs, window_ms=self.window_ms)
        sig = _receipt_sig(rec)
        write = rec.get("kind") == "haptic_receipt" or sig != self._last_sig
        self._last_sig = sig
        with self._lock:
            self._ring.append(rec)
        if write:
            self._write_jsonl(rec)

    def _write_jsonl(self, rec: dict[str, Any]) -> None:
        if not self.persist or self._jsonl is None:
            return
        try:
            self._jsonl.parent.mkdir(parents=True, exist_ok=True)
            with self._jsonl.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
        except Exception as e:
            log.debug("haptic receipt jsonl: %s", e)


_clock: HapticReceiptClock | None = None
_clock_lock = threading.Lock()


def _env_persist() -> bool:
    return os.environ.get("QORESENCE_HAPTIC_RECEIPT", "0").strip().lower() in _TRUE


def reset_receipt_clock() -> None:
    global _clock
    with _clock_lock:
        c = _clock
        _clock = None
    if c is not None:
        try:
            c.stop()
        except Exception:
            pass


def start_receipt_clock(
    *,
    persist: bool | None = None,
    jsonl_path: Path | None = None,
    out_dir: Path | str | None = None,
    session_id: str = "",
    clock: HapticReceiptClock | None = None,
) -> HapticReceiptClock:
    global _clock
    if clock is not None:
        with _clock_lock:
            old = _clock
            _clock = clock
        if old is not None and old is not clock:
            try:
                old.stop()
            except Exception:
                pass
        return clock
    on = bool(persist) if persist is not None else _env_persist()
    path = jsonl_path
    if path is None and on:
        root = Path(out_dir) if out_dir is not None else Path("logs/haptic")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (session_id or "session"))[:48]
        path = root / f"{safe}_{stamp}_receipt.jsonl"
    started = HapticReceiptClock(persist=on, jsonl_path=path)
    with _clock_lock:
        old = _clock
        _clock = started
    if old is not None and old is not started:
        try:
            old.stop()
        except Exception:
            pass
    if on:
        log.info("haptic receipt clock persist (private JSONL %s)", path)
    return started


def get_receipt_clock() -> HapticReceiptClock:
    global _clock
    with _clock_lock:
        if _clock is None:
            _clock = HapticReceiptClock(persist=_env_persist())
        return _clock


def note_tick(tick: dict[str, Any] | None) -> None:
    get_receipt_clock().note_tick(tick)


def note_obs(obs: dict[str, Any] | None) -> None:
    get_receipt_clock().note_obs(obs)


def recent_receipts(n: int = 20) -> list[dict[str, Any]]:
    c = _clock
    if c is None:
        return []
    return c.recent(n)
