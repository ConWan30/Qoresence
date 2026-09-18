"""SyncCoroner — TypeSafe semantic layer over the sync-health machine.

A timer-driven worker that reads compact sync telemetry and asks Jev *which*
bottleneck explains current lag. Code owns the mitigations: every action is a
predeclared ``SyncHealth.set_level`` — the model diagnoses, code acts.

Confidence-gated (docs/patterns/confidence-routing):
- confidence ≥ 0.7 and severity ≥ tight   → apply mapped level
- 0.4 ≤ confidence < 0.7                  → at most one soft step (smooth→tight)
- confidence < 0.4, or transient noul ≥ 0.7 → observe only, no action

Observation plane (AGENTS.md): never emits bus events, never acquires a lobe
lock, never runs on capture/HID/bus threads. No API key → a deterministic
local heuristic still runs, so the plane degrades gracefully.

Gate: same flag as the Jev conductor (``--jev`` / ``QORESENCE_JEV=1``).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from qoresence.observability.typesafe_ask import (
    DEFAULT_TIMEOUT_S,
    system_one,
)
from qoresence.sync.sync_health import SHEDDING, SMOOTH, TIGHT, get_sync_health

log = logging.getLogger(__name__)

BOTTLENECKS = (
    "healthy",
    "hid_fanout_storm",
    "gil_starvation",
    "capture_usb_contention",
    "vlm_backpressure",
    "queue_growth",
    "transient",
)

# Predeclared mitigations — the only actions the coroner may take.
_MITIGATION_LEVEL = {
    "hid_fanout_storm": SHEDDING,
    "gil_starvation": SHEDDING,
    "capture_usb_contention": SHEDDING,
    "vlm_backpressure": TIGHT,
    "queue_growth": TIGHT,
    "transient": None,  # hold — do not escalate on a transient
    "healthy": SMOOTH,
}

_CONF_ACT = 0.7
_CONF_SOFT = 0.4
_TRANSIENT_SUPPRESS = 0.7


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_JEV", "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }


def coroner_questions() -> dict[str, Any]:
    """One call: bottleneck Choice + severity Score + transient Noul."""
    try:
        from typesafe_sdk import Choice, Noul, Score
    except Exception:
        return {}
    return {
        "bottleneck": Choice(
            instructions={
                "question": (
                    "Which single bottleneck best explains the lag described "
                    "by `sync`, `hid`, `video`, and `bus` telemetry?"
                ),
                "focus": "Diagnose the dominant cause only — code owns all fixes.",
                "never": "Never prescribe a fix; classify only.",
            },
            criteria={
                "healthy": {"what": "Telemetry nominal; no lag present."},
                "hid_fanout_storm": {
                    "what": (
                        "High-rate coalesced HID emits on the bus (hid.emit_eps) "
                        "starving the capture path. Raw reports_eps is not the storm."
                    ),
                },
                "gil_starvation": {
                    "what": "Python threads contend for the GIL; grab loop starved though USB is fine.",
                },
                "capture_usb_contention": {
                    "what": "HID polling and capture card share USB bandwidth; frames drop at the driver.",
                },
                "vlm_backpressure": {
                    "what": "VLM/cloud calls in flight crowd out frame processing.",
                },
                "queue_growth": {
                    "what": "Bounded queues filling or dropping; consumers behind producers.",
                },
                "transient": {"what": "A brief spike that resolves by itself; not a steady state."},
            },
        ),
        "severity": Score(
            instructions={
                "question": "How degraded is the video pipeline right now?",
                "focus": "Rate observed telemetry, not potential.",
            },
            criteria=[
                "Smooth — fps near target, fresh frames, no queue pressure.",
                "Tight — fps sagging or age rising but recoverable without shedding.",
                "Degraded — sustained low fps or stale frames; shedding warranted.",
                "Critical — feed effectively stalled; drop everything optional.",
            ],
        ),
        "transient": Noul(
            instructions={
                "question": (
                    "Is this lag transient — a brief spike likely to self-resolve "
                    "within ~2 seconds without intervention?"
                ),
                "true": "Momentary blip (single dropped burst, startup, reconnect).",
                "false": "Sustained pressure or a standing misconfiguration.",
            },
        ),
    }


def local_coroner(snap: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fallback when the SDK/key is absent."""
    sync = snap.get("sync") or {}
    hid = snap.get("hid") or {}
    ratio = sync.get("fps_ratio")
    age = sync.get("video_age_s") or 0.0
    # emit_eps = coalesced aggregates hitting the bus; reports_eps = raw HID
    # poll rate. A fanout storm is high emit_eps — high reports_eps alone is
    # normal and must not be read as a storm.
    emit_eps = float(hid.get("emit_eps") or 0.0)

    if ratio is not None and ratio < 0.7 and emit_eps > 20.0:
        return {
            "bottleneck": "hid_fanout_storm",
            "bottleneck_confidence": 0.75,
            "severity": 2.0,
            "transient_noul": 0.2,
            "source": "local_heuristic",
        }
    if (ratio is not None and ratio < 0.4) or age > 1.0:
        return {
            "bottleneck": "capture_usb_contention",
            "bottleneck_confidence": 0.6,
            "severity": 2.0,
            "transient_noul": 0.3,
            "source": "local_heuristic",
        }
    if (ratio is not None and ratio < 0.85) or age > 0.5:
        return {
            "bottleneck": "transient",
            "bottleneck_confidence": 0.55,
            "severity": 1.0,
            "transient_noul": 0.6,
            "source": "local_heuristic",
        }
    return {
        "bottleneck": "healthy",
        "bottleneck_confidence": 0.85,
        "severity": 0.0,
        "transient_noul": 0.5,
        "source": "local_heuristic",
    }


_RANK = {SMOOTH: 0, TIGHT: 1, SHEDDING: 2}


def compose_verdict(
    *,
    bottleneck: str | None,
    bottleneck_confidence: float | None,
    severity: float | None,
    transient_noul: float | None,
    current_level: str,
) -> dict[str, Any]:
    """Code-owned policy: confidences → at most a predeclared set_level."""
    bn = bottleneck if bottleneck in BOTTLENECKS else "transient"
    conf = float(bottleneck_confidence or 0.0)
    sev = float(severity or 0.0)
    noul = float(transient_noul or 0.5)
    target = _MITIGATION_LEVEL.get(bn)
    cur_rank = _RANK.get(current_level, 0)
    tgt_rank = _RANK.get(target, cur_rank) if target is not None else cur_rank

    action = "observe"
    applied_level = None
    if noul >= _TRANSIENT_SUPPRESS and bn != "healthy":
        action = "held_transient"
    elif target is not None and tgt_rank != cur_rank:
        if tgt_rank < cur_rank:
            # De-escalation: low severity is expected — confidence alone gates.
            if conf >= _CONF_ACT:
                action = "apply"
                applied_level = target
            else:
                action = "observe_low_conf"
        elif conf >= _CONF_ACT and sev >= 1.0:
            action = "apply"
            applied_level = target
        elif conf >= _CONF_SOFT:
            # Soft gate: tighten at most one step from smooth.
            if current_level == SMOOTH:
                action = "apply"
                applied_level = TIGHT
            else:
                action = "observe_low_conf"
    return {
        "bottleneck": bn,
        "bottleneck_confidence": round(conf, 3),
        "severity": round(sev, 2),
        "transient_noul": round(noul, 3),
        "current_level": current_level,
        "target_level": target,
        "action": action,
        "applied_level": applied_level,
        "licenses_digits": False,
    }


class SyncCoroner:
    """Timer-driven semantic diagnostician. Never on the capture path."""

    def __init__(
        self,
        config: Any = None,
        *,
        sync_health: Any = None,
        bus: Any = None,
        ask_fn: Any = None,
    ) -> None:
        self.config = config
        self._health = sync_health or get_sync_health()
        self._bus = bus  # stats only — never emit, never subscribe
        self._ask_fn = ask_fn
        self.enabled = bool(getattr(config, "enabled", False)) or _env_enabled()
        self._warned_typesafe = [False]
        self._typesafe_timeout_s = float(
            getattr(config, "typesafe_timeout_s", DEFAULT_TIMEOUT_S)
            or DEFAULT_TIMEOUT_S
        )
        self._cadence_s = float(getattr(config, "cadence_s", 3.0) or 3.0)
        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._ticks = 0
        self._applied = 0
        self._suppressed = 0
        self._last: dict[str, Any] = {}
        self._last_ns = 0
        self._last_bus_events = 0
        self._last_telemetry_emitted = 0
        self._last_collect_mono: float | None = None
        self._jsonl_handle: Any = None
        if not self.enabled:
            return
        out_dir = Path(getattr(config, "out_dir", "logs/sync_coroner") or "logs/sync_coroner")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            self._jsonl_handle = (out_dir / "sync_coroner.jsonl").open("a", encoding="utf-8")
        except Exception as e:
            log.debug("sync_coroner jsonl not opened: %s", e)
        self._worker = threading.Thread(target=self._run, name="sync-coroner", daemon=True)
        self._worker.start()
        log.info("SyncCoroner started (cadence %.1fs)", self._cadence_s)

    # ── telemetry ────────────────────────────────────────────────────────

    def _collect(self) -> dict[str, Any]:
        snap: dict[str, Any] = {"sync": self._health.stats()}
        now_mono = time.monotonic()
        # Rate denominators use the real gap between collects, not cadence —
        # and the first collect has no prior sample, so eps stays None (a
        # cumulative-counter/cadence quotient would read as a false storm).
        elapsed = (
            (now_mono - self._last_collect_mono)
            if self._last_collect_mono is not None
            else None
        )
        self._last_collect_mono = now_mono
        try:
            from qoresence.sync.hid_telemetry import snapshot as _hid_snap

            snap["hid"] = _hid_snap()
        except Exception:
            snap["hid"] = {}
        try:
            from qoresence.monitor.frame_hub import get_latest_stamp

            snap["video"] = get_latest_stamp()
        except Exception:
            snap["video"] = {}
        try:
            from qoresence.lobes.controller import get_controller_runtime

            rt = get_controller_runtime()
            snap["controller"] = rt.get_stats() if rt is not None else {}
            # Coalesced bus emits/sec — the *actual* HID pressure on the bus.
            # Slot publish eps (reports) stays high by design; only emit_eps
            # can diagnose a fanout storm.
            emitted_t = int(snap["controller"].get("telemetry_emitted") or 0)
            snap.setdefault("hid", {})["emit_eps"] = (
                round(max(0, emitted_t - self._last_telemetry_emitted) / elapsed, 1)
                if elapsed
                else None
            )
            self._last_telemetry_emitted = emitted_t
        except Exception:
            snap["controller"] = {}
        if self._bus is not None:
            try:
                bs = self._bus.stats()
                emitted = int(bs.get("events_emitted") or 0)
                snap["bus_eps"] = (
                    round(max(0, emitted - self._last_bus_events) / elapsed, 1)
                    if elapsed
                    else None
                )
                self._last_bus_events = emitted
            except Exception:
                snap["bus_eps"] = None
        return snap

    # ── judging ──────────────────────────────────────────────────────────

    def _judge(self, snap: dict[str, Any]) -> dict[str, Any]:
        sync = snap.get("sync") or {}
        model_called = False
        answers = None
        if self._ask_fn is not None:
            answers = self._ask_fn(snap)
            model_called = True
        if answers is None and sync.get("level") != SMOOTH:
            # Only burn a model call when the deterministic machine already
            # sees degradation — a healthy system needs no diagnosis.
            answers = self._try_typesafe(snap)
            model_called = model_called or answers is not None
        if answers is None:
            answers = local_coroner(snap)
        verdict = compose_verdict(
            bottleneck=answers.get("bottleneck"),
            bottleneck_confidence=answers.get("bottleneck_confidence"),
            severity=answers.get("severity"),
            transient_noul=answers.get("transient_noul"),
            current_level=str(sync.get("level") or SMOOTH),
        )
        verdict["source"] = answers.get("source") or "unknown"
        verdict["model_called"] = bool(model_called)
        return verdict

    def _try_typesafe(self, snap: dict[str, Any]) -> dict[str, Any] | None:
        questions = coroner_questions()
        if not questions:
            return None
        state = {
            "policy": (
                "Diagnosis only. Code owns all mitigations, clocks, and the "
                "capture path. Never prescribe fixes."
            ),
            "sync": snap.get("sync") or {},
            "hid": snap.get("hid") or {},
            "video": snap.get("video") or {},
            "controller": snap.get("controller") or {},
            "bus_eps": snap.get("bus_eps"),
        }
        response = system_one(
            state=state,
            questions=questions,
            timeout_s=self._typesafe_timeout_s,
            warn_label="sync_coroner",
            warned_flag=self._warned_typesafe,
            logger=log,
        )
        if response is None:
            return None
        choices = getattr(response, "choices", {}) or {}
        scores = getattr(response, "scores", {}) or {}
        nouls = getattr(response, "nouls", {}) or {}
        b = choices.get("bottleneck")
        s = scores.get("severity")
        t = nouls.get("transient")
        return {
            "bottleneck": getattr(b, "choice", None) if b is not None else None,
            "bottleneck_confidence": (
                float(getattr(b, "confidence", 0) or 0) if b is not None else None
            ),
            "severity": float(s.score) if s is not None else None,
            "transient_noul": float(t.noul) if t is not None else None,
            "source": "typesafe",
        }

    def _apply(self, verdict: dict[str, Any]) -> None:
        if verdict.get("action") == "apply" and verdict.get("applied_level"):
            self._health.set_level(
                verdict["applied_level"],
                reason=verdict.get("bottleneck") or "coroner",
                source="sync_coroner",
            )
            self._applied += 1
        elif verdict.get("action") == "held_transient":
            self._suppressed += 1

    def _run(self) -> None:
        while not self._stop_evt.wait(self._cadence_s):
            try:
                snap = self._collect()
                verdict = self._judge(snap)
                self._apply(verdict)
                verdict["tick"] = self._ticks
                verdict["ts"] = time.time()
                with self._lock:
                    self._last = verdict
                    self._last_ns = time.monotonic_ns()
                    self._ticks += 1
                self._write_jsonl(verdict)
            except Exception as e:
                log.debug("sync_coroner tick failed: %s", e)

    def _write_jsonl(self, row: dict[str, Any]) -> None:
        handle = self._jsonl_handle
        if handle is None:
            return
        try:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            handle.flush()
        except Exception:
            pass

    def stats(self) -> dict[str, Any]:
        with self._lock:
            last = dict(self._last)
            ticks, applied, suppressed = self._ticks, self._applied, self._suppressed
            last_ns = self._last_ns
        age = None
        if last_ns:
            age = round((time.monotonic_ns() - last_ns) / 1e9, 3)
        return {
            "enabled": bool(self.enabled),
            "ticks": ticks,
            "applied": applied,
            "suppressed": suppressed,
            "last_age_s": age,
            "bottleneck": last.get("bottleneck"),
            "bottleneck_confidence": last.get("bottleneck_confidence"),
            "severity": last.get("severity"),
            "action": last.get("action"),
            "source": last.get("source"),
            "licenses_digits": False,
        }

    def stop(self) -> None:
        self._stop_evt.set()
        if self._jsonl_handle is not None:
            try:
                self._jsonl_handle.close()
            except Exception:
                pass
            self._jsonl_handle = None


_singleton: SyncCoroner | None = None
_singleton_lock = threading.Lock()


def get_sync_coroner() -> SyncCoroner | None:
    with _singleton_lock:
        return _singleton


def make_coroner_from_config(
    config: Any, *, bus: Any = None, ask_fn: Any = None
) -> SyncCoroner | None:
    enabled = bool(getattr(config, "enabled", False)) or _env_enabled()
    if not enabled:
        return None
    cor = SyncCoroner(config, bus=bus, ask_fn=ask_fn)
    if not cor.enabled:
        return None
    global _singleton
    with _singleton_lock:
        _singleton = cor
    return cor
