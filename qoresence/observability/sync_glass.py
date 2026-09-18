"""SyncGlass v0 — Jev judgment pack for pad↔picture bind glass.

Speculative fan-out (one ``system_one`` call) + confidence-gated routing.
Code owns consequences. Glyphs only: bind / lag / haptic. v0 is advisory —
never applies ``lag_center`` recenter, never changes capture fps, never
authors haptics.

Same shape as ticket_glass / ticket_stale / SyncCoroner (AGENTS.md Rules 5–6):

1. ``_on_event`` only enqueues (bounded, drop-oldest). Never blocks, never
   emits, never acquires a lobe lock. Grab waits for nobody.
2. A daemon worker on a cadence timer judges compact text state via TypeSafe,
   falling back to a deterministic local heuristic (fail-closed **dark /
   observe**) when the SDK/key is absent.
3. ``licenses_digits`` is False forever. ``recenter_applied`` and
   ``capture_fps_changed`` are False forever in v0.
4. DualSense topology: USB laptop observe + BT PS5 play. Equalize via
   video-clock bind facts only. No Truth-plane / QorTroller wrap.

Opt-in: ``--sync-glass`` / ``QORESENCE_SYNC_GLASS=1``, or under the
Jev umbrella ``--jev`` / ``QORESENCE_JEV=1``. ``--play`` does not enable.
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

from qoresence.observability.sync_glass_questions import (
    ACTIONS,
    BIND_HEALTHY_ACT,
    BIND_HEALTHY_NOT,
    BIND_STATES,
    CONF_ACT,
    CONF_RECENTER,
    CONF_SOFT,
    HAPTIC_COUPLED_ACT,
    HAPTIC_COUPLED_NOT,
    HAPTIC_STATES,
    HID_SOURCES,
    LAG_CLASSES,
    sync_glass_questions,
)

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"
MODEL = "jev-latest"

# Situation ticks stay fast for /health freshness; TypeSafe asks are slower.
_ASK_INTERVAL_S = 2.0
_TYPESAFE_REUSE_S = 15.0
_TYPESAFE_TIMEOUT_S = 10.0

_PIXEL_KEYS = frozenset(
    {
        "jpeg",
        "jpg",
        "png",
        "frame",
        "image",
        "base64",
        "pixels",
        "hdmi",
        "crop_jpeg",
        "frame_jpeg",
        "thumbnail",
    }
)
_TRUTH_KEYS = frozenset(
    {"truth", "qortroller", "humanity", "eligibility", "anti_cheat", "truth_plane"}
)

_LAST_N = 8
_OK_BAND_MS = 40.0
_STARVE_AGE_S = 1.0


def _truthy(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in {"1", "true", "on", "yes"}


def _env_enabled() -> bool:
    return _truthy("QORESENCE_SYNC_GLASS") or _truthy("QORESENCE_JEV")


def _key_present() -> bool:
    if os.environ.get("TYPESAFE_API_KEY", "").strip():
        return True
    try:
        p = Path(".secrets/typesafe.key")
        return p.is_file() and bool(p.stat().st_size)
    except Exception:
        return False


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _norm_float(v: Any, default: float | None = None) -> float | None:
    if v in (None, ""):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _band(conf: float) -> str:
    if conf < CONF_SOFT:
        return "observe"
    if conf < CONF_ACT:
        return "soft"
    return "act"


def _clamp_severity(score: Any) -> int:
    try:
        n = int(round(float(score)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(3, n))


def _noul_band(noul: float | None, act: float, not_act: float) -> str:
    if noul is None:
        return "observe"
    if noul >= act:
        return "act"
    if noul <= not_act:
        return "act"
    return "soft"


def _sanitize(obj: Any, depth: int = 0) -> Any:
    """Drop pixels and Truth-plane wrap. Text / numbers / enums only."""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            key = str(k)
            low = key.lower()
            if low in _PIXEL_KEYS or low in _TRUTH_KEYS or "base64" in low:
                continue
            if "jpeg" in low or "png" in low:
                continue
            out[key] = _sanitize(v, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [_sanitize(x, depth + 1) for x in obj[:_LAST_N]]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def compose_sync_verdict(
    *,
    bind_healthy: float | None = None,
    lag_class: str | None = None,
    lag_confidence: float | None = None,
    haptic_coupled: float | None = None,
    action: str | None = None,
    action_confidence: float | None = None,
    severity: float | None = None,
    severity_confidence: float | None = None,
) -> dict[str, Any]:
    """Code-owned policy. Confidence bands: >=0.7 act / 0.4-0.7 soft / <0.4 observe.

    ``recenter_soft`` needs conf>=0.85 to surface, and v0 still does **not**
    apply PLL recenter or change capture fps. Ambiguous → observe.
    Glyphs fail-closed. ``licenses_digits`` is False on every output forever.
    """
    bind_noul = _norm_float(bind_healthy)
    hap_noul = _norm_float(haptic_coupled)
    l_conf = float(lag_confidence or 0.0)
    a_conf = float(action_confidence or 0.0)
    s_conf = float(severity_confidence or 0.0)

    raw_lag = lag_class if lag_class in LAG_CLASSES else "unknown"
    lag_acted = raw_lag if l_conf >= CONF_SOFT else "unknown"

    if bind_noul is None:
        bind_glyph = "unknown"
    elif bind_noul >= BIND_HEALTHY_ACT:
        bind_glyph = "ok"
    elif bind_noul <= BIND_HEALTHY_NOT:
        bind_glyph = "off"
    else:
        bind_glyph = "soft"
    if bind_glyph not in BIND_STATES:
        bind_glyph = "unknown"

    if hap_noul is None:
        haptic_glyph = "unknown"
    elif hap_noul >= HAPTIC_COUPLED_ACT:
        haptic_glyph = "on"
    elif hap_noul <= HAPTIC_COUPLED_NOT:
        haptic_glyph = "off"
    else:
        haptic_glyph = "unknown"
    if haptic_glyph not in HAPTIC_STATES:
        haptic_glyph = "unknown"

    raw_action = action if action in ACTIONS else "observe"
    if raw_action == "recenter_soft":
        action_acted = "recenter_soft" if a_conf >= CONF_RECENTER else "observe"
    elif a_conf < CONF_ACT:
        action_acted = "observe"
    else:
        action_acted = raw_action
    if lag_acted == "unknown" and bind_glyph == "unknown":
        if raw_action == "dark_overlay" and a_conf >= CONF_ACT:
            action_acted = "dark_overlay"
        else:
            action_acted = "observe"
    if action_acted not in ACTIONS:
        action_acted = "observe"

    sev = _clamp_severity(severity) if s_conf >= CONF_SOFT else 0

    return {
        "plane": PLANE,
        "licenses_digits": False,
        "recenter_applied": False,
        "capture_fps_changed": False,
        "haptic_authored": False,
        "bind_healthy": round(bind_noul, 3) if bind_noul is not None else None,
        "lag_class": lag_acted,
        "lag_class_raw": raw_lag,
        "lag_confidence": round(l_conf, 3),
        "haptic_coupled": round(hap_noul, 3) if hap_noul is not None else None,
        "action": action_acted,
        "action_raw": raw_action,
        "action_confidence": round(a_conf, 3),
        "severity": sev,
        "severity_confidence": round(s_conf, 3),
        "glyphs": {
            "bind": bind_glyph,
            "lag": lag_acted,
            "haptic": haptic_glyph,
        },
        "bands": {
            "lag_class": _band(l_conf),
            "action": _band(a_conf),
            "severity": _band(s_conf),
            "bind_healthy": _noul_band(bind_noul, BIND_HEALTHY_ACT, BIND_HEALTHY_NOT),
            "haptic_coupled": _noul_band(hap_noul, HAPTIC_COUPLED_ACT, HAPTIC_COUPLED_NOT),
        },
    }


def local_sync_answers(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in when the SDK/key is absent.

    Fail-closed **dark/observe**: never surfaces ``recenter_soft`` (no Jev
    conf≥0.85). Classifies lag from stamped bind facts only.
    """
    state = state if isinstance(state, dict) else {}
    video = state.get("video") if isinstance(state.get("video"), dict) else {}
    hid = state.get("hid") if isinstance(state.get("hid"), dict) else {}
    haptic = state.get("haptic") if isinstance(state.get("haptic"), dict) else {}
    capture = state.get("capture") if isinstance(state.get("capture"), dict) else {}

    age = _norm_float(video.get("age_s"))
    starve = bool(capture.get("starve")) or (age is not None and age >= _STARVE_AGE_S)
    source = str(hid.get("source") or "empty")
    if source not in HID_SOURCES:
        source = "empty"
    edges = hid.get("edges_last_n") if isinstance(hid.get("edges_last_n"), list) else []
    lag = _norm_float(hid.get("sync_lag_ms"))
    center = _norm_float(hid.get("lag_center_ms"))
    pll = video.get("pll_lock")
    co_occur = bool(haptic.get("co_occur_recent"))
    probe_ok = haptic.get("probe_ok")

    has_video = (
        age is not None or video.get("frames") is not None or video.get("pll_lock") is not None
    )
    hid_empty = source == "empty" and not edges

    if starve:
        cls, l_conf, bind_noul, sev = "capture_starve", 0.85, 0.12, 3
        action, a_conf = "flag_operator", 0.9
    elif hid_empty and has_video:
        # Path B: DualSense on PS5, laptop USB empty, picture still live.
        cls, l_conf, bind_noul, sev = "hid_empty_usb", 0.85, 0.22, 1
        action, a_conf = "observe", 0.9
    elif lag is not None and center is not None:
        delta = lag - center
        if delta > _OK_BAND_MS:
            cls, l_conf, bind_noul, sev = "picture_ahead", 0.8, 0.35, 2
            action, a_conf = "observe", 0.9
        elif delta < -_OK_BAND_MS:
            cls, l_conf, bind_noul, sev = "pad_ahead", 0.8, 0.35, 2
            action, a_conf = "observe", 0.9
        else:
            cls, l_conf = "ok", 0.85
            bind_noul = 0.82 if pll else 0.62
            sev = 0
            action, a_conf = "observe", 0.9
    elif lag is not None and abs(lag) > _OK_BAND_MS:
        if lag > 0:
            cls, l_conf, bind_noul, sev = "picture_ahead", 0.7, 0.38, 2
        else:
            cls, l_conf, bind_noul, sev = "pad_ahead", 0.7, 0.38, 2
        action, a_conf = "observe", 0.9
    elif source in {"usb_play", "bt"} and (pll or (age is not None and age < 0.5)):
        cls, l_conf, bind_noul, sev = "ok", 0.7, 0.72, 0
        action, a_conf = "observe", 0.9
    else:
        cls, l_conf, bind_noul, sev = "unknown", 0.0, None, 0
        action, a_conf = "dark_overlay", 0.9

    # Haptic glyph needs --haptic-probe (probe_ok). Without it stay dark/off —
    # do not soft-unknown from absence alone. co_occur_recent comes from
    # probe.recent() (imu_echo / hid_output); never invent vibration_burst fields.
    if co_occur:
        hap_noul, h_conf = 0.82, 0.9
    elif probe_ok is False:
        hap_noul, h_conf = 0.12, 0.9
    elif probe_ok is None:
        # Probe default OFF → glyph off (not soft/unknown).
        hap_noul, h_conf = 0.18, 0.85
    else:
        # Probe on, no recent co-occurrence → off.
        hap_noul, h_conf = 0.18, 0.85

    return {
        "bind_healthy": bind_noul,
        "lag_class": cls,
        "lag_confidence": l_conf,
        "haptic_coupled": hap_noul,
        "haptic_confidence": h_conf,
        "action": action,
        "action_confidence": a_conf,
        "severity": float(sev),
        "severity_confidence": 0.9,
        "source": "local_heuristic",
    }


class SyncGlassSentinel:
    """Enqueue-only bus subscriber + timer worker. Never on the capture path."""

    def __init__(
        self,
        config: Any = None,
        *,
        bus: Any = None,
        ask_fn: Any = None,
        state_fn: Any = None,
        jev_enabled: bool = False,
    ) -> None:
        self.config = config
        self._bus = bus  # subscribe only — never emit
        self._ask_fn = ask_fn
        self._state_fn = state_fn
        self._lock = threading.Lock()
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(
            maxsize=int(getattr(config, "queue_size", 256) or 256)
        )
        self._dropped = 0
        self._ticks = 0
        self._judged = 0
        self._last: dict[str, Any] = {}
        self._last_ns = 0
        self._latest_live: dict[str, Any] = {}
        self._edges: deque[str] = deque(maxlen=_LAST_N)
        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None
        self._unsubscribe: Any = None
        self._jsonl_handle: Any = None
        self._cadence_s = float(getattr(config, "cadence_s", 0.5) or 0.5)
        self._ask_interval_s = _env_float(
            "QORESENCE_SYNC_GLASS_ASK_S",
            float(getattr(config, "ask_interval_s", _ASK_INTERVAL_S) or _ASK_INTERVAL_S),
        )
        self._typesafe_timeout_s = _env_float(
            "QORESENCE_SYNC_GLASS_TIMEOUT_S", _TYPESAFE_TIMEOUT_S
        )
        self._last_typesafe_answers: dict[str, Any] | None = None
        self._last_typesafe_ask_mono = 0.0
        self._last_typesafe_ok_mono = 0.0
        self._typesafe_asks = 0
        self._typesafe_fails = 0
        self._warned_typesafe = False
        enabled = bool(getattr(config, "enabled", False)) if config is not None else False
        self.enabled = enabled or bool(jev_enabled) or _env_enabled()
        if not self.enabled:
            return
        out_dir = Path(getattr(config, "out_dir", "logs/sync_glass") or "logs/sync_glass")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            self._jsonl_handle = (out_dir / "sync_glass.jsonl").open("a", encoding="utf-8")
        except Exception as e:
            log.debug("sync_glass jsonl not opened: %s", e)
        if bus is not None:
            try:
                self._unsubscribe = bus.subscribe_raw(self._on_event)
            except Exception:
                try:
                    self._unsubscribe = bus.subscribe(self._on_event)
                except Exception as e:
                    log.debug("sync_glass bus subscribe skipped: %s", e)
        self._worker = threading.Thread(target=self._run, name="sync-glass-sentinel", daemon=True)
        self._worker.start()

    # ── hot path: enqueue only (Rule-5 class) ────────────────────────────

    def _on_event(self, ev: Any) -> None:
        if not self.enabled:
            return
        try:
            payload = getattr(ev, "payload", None)
            if not isinstance(payload, dict):
                payload = ev if isinstance(ev, dict) else None
            if not isinstance(payload, dict):
                return
            et = str(getattr(ev, "type", None) or payload.get("type") or "")
            rec: dict[str, Any] = {
                "clock_ns": int(getattr(ev, "clock_ns", 0) or payload.get("clock_ns") or 0),
                "frame_seq": payload.get("frame_seq") or payload.get("seq"),
                "type": et,
            }
            edge = payload.get("hid_button") or payload.get("button") or payload.get("edge")
            if edge:
                rec["edge"] = str(edge)[:32]
            for key in (
                "age_s",
                "frames",
                "starve",
                "sync_lag_ms",
                "syncLagMs",
                "hid_at_ns",
                "hidAt",
                "lag_center_ms",
                "pll_lock",
                "co_occur_recent",
            ):
                if key in payload and payload[key] is not None:
                    rec[key] = payload[key]
            hid = payload.get("hid")
            if isinstance(hid, dict):
                rec["hid"] = {
                    k: hid.get(k)
                    for k in ("source", "sync_lag_ms", "hid_at_ns", "lag_center_ms")
                    if hid.get(k) is not None
                }
            video = payload.get("video")
            if isinstance(video, dict):
                rec["video"] = {
                    k: video.get(k)
                    for k in ("age_s", "frames", "pll_lock")
                    if video.get(k) is not None
                }
            if (
                rec.get("frame_seq") is None
                and "edge" not in rec
                and "age_s" not in rec
                and "sync_lag_ms" not in rec
                and "syncLagMs" not in rec
                and "hid" not in rec
                and "video" not in rec
                and "starve" not in rec
                and "co_occur_recent" not in rec
            ):
                return
            try:
                self._queue.put_nowait(rec)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                self._dropped += 1
                try:
                    self._queue.put_nowait(rec)
                except queue.Full:
                    self._dropped += 1
        except Exception:
            return

    # ── state collection (read-only accessors, never mutators) ───────────

    def _drain_live(self) -> None:
        """Fold queued live records into _latest_live (worker thread only)."""
        while True:
            try:
                rec = self._queue.get_nowait()
            except queue.Empty:
                return
            live: dict[str, Any] = {
                "clock_ns": rec.get("clock_ns"),
                "frame_seq": rec.get("frame_seq"),
            }
            hid = rec.get("hid") if isinstance(rec.get("hid"), dict) else {}
            video = rec.get("video") if isinstance(rec.get("video"), dict) else {}
            live["age_s"] = rec.get("age_s") if rec.get("age_s") is not None else video.get("age_s")
            live["frames"] = (
                rec.get("frames") if rec.get("frames") is not None else video.get("frames")
            )
            live["pll_lock"] = (
                rec.get("pll_lock") if rec.get("pll_lock") is not None else video.get("pll_lock")
            )
            live["starve"] = rec.get("starve")
            live["sync_lag_ms"] = (
                rec.get("sync_lag_ms")
                if rec.get("sync_lag_ms") is not None
                else rec.get("syncLagMs")
                if rec.get("syncLagMs") is not None
                else hid.get("sync_lag_ms")
            )
            live["hid_at_ns"] = (
                rec.get("hid_at_ns")
                if rec.get("hid_at_ns") is not None
                else rec.get("hidAt")
                if rec.get("hidAt") is not None
                else hid.get("hid_at_ns")
            )
            live["lag_center_ms"] = (
                rec.get("lag_center_ms")
                if rec.get("lag_center_ms") is not None
                else hid.get("lag_center_ms")
            )
            live["hid_source"] = hid.get("source")
            live["co_occur_recent"] = rec.get("co_occur_recent")
            with self._lock:
                self._latest_live.update({k: v for k, v in live.items() if v is not None})
                if rec.get("edge"):
                    self._edges.append(str(rec["edge"]))

    def _ticket_glass_facts(self) -> dict[str, Any]:
        try:
            from qoresence.observability.ticket_glass import get_ticket_glass

            sen = get_ticket_glass()
            if sen is None:
                return {"lock": None, "enabled": False}
            st = sen.stats() or {}
            glyphs = st.get("glyphs") if isinstance(st.get("glyphs"), dict) else {}
            return {
                "lock": glyphs.get("lock"),
                "enabled": bool(st.get("enabled")),
            }
        except Exception:
            return {"lock": None, "enabled": False}

    def _video_state(self, live: dict[str, Any]) -> dict[str, Any]:
        video: dict[str, Any] = {
            "age_s": live.get("age_s"),
            "frames": live.get("frames"),
            "pll_lock": live.get("pll_lock"),
        }
        try:
            from qoresence.monitor.frame_hub import get_latest_stamp

            stamp = get_latest_stamp() or {}
            if video["age_s"] is None:
                video["age_s"] = stamp.get("age_s")
            if video["frames"] is None:
                video["frames"] = stamp.get("seq")
            if live.get("clock_ns") in (None, 0) and stamp.get("clock_ns"):
                live["clock_ns"] = stamp.get("clock_ns")
            if live.get("frame_seq") in (None, 0) and stamp.get("seq"):
                live["frame_seq"] = stamp.get("seq")
        except Exception:
            pass
        try:
            from qoresence.sync.lag_estimator import get_lag_estimator

            pll = get_lag_estimator().snapshot() or {}
            if video["pll_lock"] is None:
                video["pll_lock"] = bool(pll.get("pll_lock"))
            live.setdefault("lag_center_ms", pll.get("lag_center_ms"))
        except Exception:
            pass
        try:
            from qoresence.sync.ivc import get_last_coupling

            coup = get_last_coupling() or {}
            if video["pll_lock"] is None:
                video["pll_lock"] = bool(coup.get("pll_lock"))
            if live.get("lag_center_ms") is None:
                live["lag_center_ms"] = coup.get("lag_center_ms")
            if live.get("sync_lag_ms") is None:
                live["sync_lag_ms"] = coup.get("last_bind_ms") or coup.get("lag_center_ms")
            if live.get("frame_seq") in (None, 0) and coup.get("frame_seq"):
                live["frame_seq"] = coup.get("frame_seq")
        except Exception:
            pass
        return video

    def _hid_state(self, live: dict[str, Any]) -> dict[str, Any]:
        # DualSense: USB on this laptop is observe; BT on the PS5 is play.
        # Empty USB is Path B (honest) — equalize via video-clock bind facts.
        hid: dict[str, Any] = {
            "source": str(live.get("hid_source") or "empty"),
            "edges_last_n": [],
            "apm": 0.0,
            "stick_heat": 0.0,
            "hid_at_ns": live.get("hid_at_ns"),
            "sync_lag_ms": live.get("sync_lag_ms"),
            "lag_center_ms": live.get("lag_center_ms"),
        }
        with self._lock:
            hid["edges_last_n"] = list(self._edges)
        try:
            from qoresence.sync.hid_telemetry import snapshot as _hid_snap

            snap = _hid_snap() or {}
            stick = snap.get("stick") if isinstance(snap.get("stick"), dict) else {}
            heat = 0.0
            hid_at = hid["hid_at_ns"]
            for v in stick.values():
                if isinstance(v, dict):
                    heat = max(heat, abs(float(v.get("dx") or 0)), abs(float(v.get("dy") or 0)))
                    if hid_at is None and v.get("clock_ns"):
                        hid_at = v.get("clock_ns")
            hid["stick_heat"] = round(heat, 3)
            hid["apm"] = float(snap.get("reports_eps") or 0.0)
            tremor = snap.get("tremor") if isinstance(snap.get("tremor"), dict) else None
            if hid_at is None and tremor and tremor.get("clock_ns"):
                hid_at = tremor.get("clock_ns")
            hid["hid_at_ns"] = hid_at
            if snap.get("tremor") or stick or hid["apm"] > 0:
                hid["source"] = "usb_play"
        except Exception:
            pass
        if hid["source"] not in HID_SOURCES:
            hid["source"] = "empty"
        if hid["sync_lag_ms"] is None and hid["hid_at_ns"] and live.get("clock_ns"):
            try:
                hid["sync_lag_ms"] = round((int(live["clock_ns"]) - int(hid["hid_at_ns"])) / 1e6, 3)
            except (TypeError, ValueError):
                pass
        return hid

    def _haptic_state(self, live: dict[str, Any]) -> dict[str, Any]:
        """Probe-backed haptic facts only (default OFF).

        SyncGlass haptic glyph lights from ``co_occur_recent`` via
        ``get_haptic_probe().recent()`` (``imu_echo`` / ``hid_output``).
        Requires ``--haptic-probe`` / ``QORESENCE_HAPTIC_PROBE=1``. USB does
        not carry PS5 BT rumble *output* packets — physical rumble on a
        laptop-bodied DualSense appears as ``imu_echo`` via EchoDetector.
        """
        haptic: dict[str, Any] = {
            "co_occur_recent": bool(live.get("co_occur_recent")),
            "probe_ok": None,
        }
        try:
            from qoresence.sync.haptic_probe import get_haptic_probe

            probe = get_haptic_probe()
            if probe is None:
                haptic["probe_ok"] = None
                return haptic
            haptic["probe_ok"] = True
            recent = probe.recent(n=8) if hasattr(probe, "recent") else []
            for rec in reversed(list(recent or [])):
                if not isinstance(rec, dict):
                    continue
                prov = rec.get("provenance") if isinstance(rec.get("provenance"), dict) else {}
                if rec.get("coupled") or prov.get("in_ivc_window"):
                    haptic["co_occur_recent"] = True
                    break
        except Exception:
            haptic["probe_ok"] = None
        return haptic

    def _capture_state(self, live: dict[str, Any], video: dict[str, Any]) -> dict[str, Any]:
        age = _norm_float(video.get("age_s"))
        starve = bool(live.get("starve"))
        if not starve and age is not None and age >= _STARVE_AGE_S:
            starve = True
        # Fresh picture wins over a flaky sync_health fps_ratio (<0.4 while
        # age_s is still sub-second was freezing bind=off under local_heuristic).
        fresh = age is not None and age < 0.5
        if not starve and not fresh:
            try:
                from qoresence.sync.sync_health import get_sync_health

                st = get_sync_health().stats() or {}
                ratio = _norm_float(st.get("fps_ratio"))
                vage = _norm_float(st.get("video_age_s"))
                if vage is not None and vage >= _STARVE_AGE_S:
                    starve = True
                elif (
                    ratio is not None
                    and ratio < 0.4
                    and (age is None or age >= _STARVE_AGE_S)
                ):
                    starve = True
            except Exception:
                pass
        dshow = None
        try:
            from qoresence.lobes.streamer import get_streamer_runtime

            rt = get_streamer_runtime()
            if rt is not None:
                stats = rt.get_stats() if hasattr(rt, "get_stats") else {}
                dshow = stats.get("device_name") if isinstance(stats, dict) else None
        except Exception:
            dshow = None
        return {"starve": bool(starve), "dshow_name": dshow}

    def _collect_state(self) -> dict[str, Any]:
        if self._state_fn is not None:
            try:
                s = self._state_fn()
                if isinstance(s, dict):
                    return _sanitize(s)
            except Exception:
                pass
        self._drain_live()
        with self._lock:
            live = dict(self._latest_live)
        video = self._video_state(live)
        hid = self._hid_state(live)
        haptic = self._haptic_state(live)
        capture = self._capture_state(live, video)
        ticket = self._ticket_glass_facts()
        clock_ns = int(live.get("clock_ns") or 0)
        return _sanitize(
            {
                "clock_ns": clock_ns,
                "frame_seq": live.get("frame_seq") or 0,
                "video": video,
                "hid": hid,
                "haptic": haptic,
                "capture": capture,
                "ticket_glass": ticket,
            }
        )

    # ── judging ──────────────────────────────────────────────────────────

    def _answers_with_typesafe_cadence(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Ask TypeSafe on a slower cadence; reuse last good vote between asks."""
        now = time.monotonic()
        if (now - self._last_typesafe_ask_mono) >= self._ask_interval_s:
            self._last_typesafe_ask_mono = now
            self._typesafe_asks += 1
            got = self._try_typesafe(state)
            if got is not None:
                self._last_typesafe_answers = dict(got)
                self._last_typesafe_ok_mono = now
                return got
            self._typesafe_fails += 1
        if (
            self._last_typesafe_answers is not None
            and (now - self._last_typesafe_ok_mono) < _TYPESAFE_REUSE_S
        ):
            return dict(self._last_typesafe_answers)
        return None

    def _judge(self, state: dict[str, Any]) -> dict[str, Any]:
        answers = None
        if self._ask_fn is not None:
            answers = self._ask_fn(state)
        if answers is None:
            answers = self._answers_with_typesafe_cadence(state)
        if answers is None:
            answers = local_sync_answers(state)
        verdict = compose_sync_verdict(
            bind_healthy=answers.get("bind_healthy"),
            lag_class=answers.get("lag_class"),
            lag_confidence=answers.get("lag_confidence"),
            haptic_coupled=answers.get("haptic_coupled"),
            action=answers.get("action"),
            action_confidence=answers.get("action_confidence"),
            severity=answers.get("severity"),
            severity_confidence=answers.get("severity_confidence"),
        )
        verdict["source"] = answers.get("source") or "unknown"
        return verdict

    def _try_typesafe(self, state: dict[str, Any]) -> dict[str, Any] | None:
        if not os.environ.get("TYPESAFE_API_KEY", "").strip():
            try:
                raw = Path(".secrets/typesafe.key").read_text(encoding="utf-8-sig").strip()
                if not raw:
                    return None
                os.environ["TYPESAFE_API_KEY"] = raw
            except Exception:
                return None
        try:
            from typesafe_sdk import TypeSafeClient
        except Exception:
            return None
        questions = sync_glass_questions()
        if not questions:
            return None
        payload = {
            "policy": (
                "Observation only. Never mint, restate, or license score "
                "digits. Never apply lag_center recenter. Never change "
                "capture fps. DualSense USB is laptop observe; BT on the "
                "PS5 is play. Equalize via video-clock bind facts only. "
                "No haptic authorship. No Truth-plane. Code owns clocks. "
                "Ambiguous → observe."
            ),
            "clock_ns": state.get("clock_ns"),
            "frame_seq": state.get("frame_seq"),
            "video": state.get("video") or {},
            "hid": state.get("hid") or {},
            "haptic": state.get("haptic") or {},
            "capture": state.get("capture") or {},
            "ticket_glass": state.get("ticket_glass") or {},
        }
        model = os.environ.get("QORESENCE_SYNC_GLASS_MODEL", "").strip() or MODEL
        try:
            retry_kw: dict[str, Any] = {}
            try:
                from typesafe_sdk import RetryPolicy

                retry_kw["retry"] = RetryPolicy(max_retries=0)
            except Exception:
                pass
            try:
                client_cm = TypeSafeClient(
                    model=model, timeout=self._typesafe_timeout_s, **retry_kw
                )
            except TypeError:
                try:
                    client_cm = TypeSafeClient(model=model, timeout=self._typesafe_timeout_s)
                except TypeError:
                    try:
                        client_cm = TypeSafeClient(model=model)
                    except TypeError:
                        client_cm = TypeSafeClient()
            with client_cm as client:
                try:
                    response = client.system_one(
                        state=payload,
                        questions=questions,
                        timeout=self._typesafe_timeout_s,
                    )
                except TypeError:
                    response = client.system_one(state=payload, questions=questions)
            choices = getattr(response, "choices", None) or {}
            nouls = getattr(response, "nouls", None) or {}
            scores = getattr(response, "scores", None) or {}
            if not choices and not nouls and not scores:
                answers = getattr(response, "answers", None) or {}
                for name, ans in answers.items():
                    kind = getattr(ans, "type", None) or (
                        ans.get("type") if isinstance(ans, dict) else None
                    )
                    if kind == "choice":
                        choices[name] = ans
                    elif kind == "noul":
                        nouls[name] = ans
                    elif kind == "score":
                        scores[name] = ans
            bh = nouls.get("bind_healthy")
            lc = choices.get("lag_class")
            hc = nouls.get("haptic_coupled")
            act = choices.get("action")
            sev = scores.get("severity")
            return {
                "bind_healthy": float(bh.noul) if bh is not None else None,
                "lag_class": getattr(lc, "choice", None) if lc is not None else None,
                "lag_confidence": (
                    float(getattr(lc, "confidence", 0) or 0) if lc is not None else None
                ),
                "haptic_coupled": float(hc.noul) if hc is not None else None,
                "action": getattr(act, "choice", None) if act is not None else None,
                "action_confidence": (
                    float(getattr(act, "confidence", 0) or 0) if act is not None else None
                ),
                "severity": float(sev.score) if sev is not None else None,
                "severity_confidence": (
                    float(getattr(sev, "confidence", 0) or 0) if sev is not None else None
                ),
                "source": "typesafe",
            }
        except Exception as e:
            if not self._warned_typesafe:
                self._warned_typesafe = True
                log.warning(
                    "sync_glass system_one failed (%s): %s",
                    type(e).__name__,
                    e,
                )
            else:
                log.debug("sync_glass system_one failed: %s", e)
            return None

    # ── worker ───────────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_evt.wait(self._cadence_s):
            try:
                state = self._collect_state()
                verdict = self._judge(state)
                verdict["tick"] = self._ticks
                verdict["ts"] = time.time()
                with self._lock:
                    self._last = verdict
                    self._last_ns = time.monotonic_ns()
                    self._ticks += 1
                    self._judged += 1
                self._write_jsonl(verdict)
            except Exception as e:
                log.debug("sync_glass tick failed: %s", e)

    def _write_jsonl(self, row: dict[str, Any]) -> None:
        handle = self._jsonl_handle
        if handle is None:
            return
        try:
            handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
            handle.flush()
        except Exception:
            pass

    def last(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            last = dict(self._last)
            ticks, judged, dropped = self._ticks, self._judged, self._dropped
            last_ns = self._last_ns
        age = None
        if last_ns:
            age = round((time.monotonic_ns() - last_ns) / 1e9, 3)
        glyphs = last.get("glyphs") if isinstance(last.get("glyphs"), dict) else {}
        return {
            "enabled": bool(self.enabled),
            "key_present": _key_present(),
            "ticks": ticks,
            "judged": judged,
            "dropped": dropped,
            "last_age_s": age,
            "glyphs": {
                "bind": glyphs.get("bind"),
                "lag": glyphs.get("lag"),
                "haptic": glyphs.get("haptic"),
            },
            "lag_class": last.get("lag_class"),
            "action": last.get("action"),
            "severity": last.get("severity"),
            "bind_healthy": last.get("bind_healthy"),
            "haptic_coupled": last.get("haptic_coupled"),
            "source": last.get("source"),
            "typesafe_asks": self._typesafe_asks,
            "typesafe_fails": self._typesafe_fails,
            "ask_interval_s": self._ask_interval_s,
            "licenses_digits": False,
            "recenter_applied": False,
            "capture_fps_changed": False,
            "haptic_authored": False,
        }

    def stop(self) -> None:
        self._stop_evt.set()
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            except Exception:
                pass
            self._unsubscribe = None
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=2.0)
        if self._jsonl_handle is not None:
            try:
                self._jsonl_handle.close()
            except Exception:
                pass
            self._jsonl_handle = None


_singleton: SyncGlassSentinel | None = None
_singleton_lock = threading.Lock()


def get_sync_glass() -> SyncGlassSentinel | None:
    with _singleton_lock:
        return _singleton


def make_sync_glass_from_config(
    config: Any,
    *,
    bus: Any = None,
    jev_enabled: bool = False,
    ask_fn: Any = None,
    state_fn: Any = None,
) -> SyncGlassSentinel | None:
    enabled = bool(getattr(config, "enabled", False)) or jev_enabled or _env_enabled()
    if not enabled:
        return None
    sen = SyncGlassSentinel(
        config,
        bus=bus,
        ask_fn=ask_fn,
        state_fn=state_fn,
        jev_enabled=jev_enabled,
    )
    if not sen.enabled:
        return None
    global _singleton
    with _singleton_lock:
        _singleton = sen
    return sen
