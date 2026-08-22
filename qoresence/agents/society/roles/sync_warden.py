"""Sync Warden — DualSense ↔ HDMI coupling monitor. Observation only.

Never opens capture. Never emits bus events. Never takes a lobe lock.
Reports PLL / lag / IMU body / Ghost Stick paint. Optional Quicksilver note.
"""

from __future__ import annotations

import json
from typing import Any

from qoresence.agents.society.types import AgentPacket, AgentReceipt

_STALE_AGE_S = 0.35
_LAG_WIDE_MS = 160.0
_JITTER_WIDE_MS = 28.0


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def inspect(packet: AgentPacket) -> dict[str, Any]:
    health = packet.health or {}
    coup = health.get("coupling") if isinstance(health.get("coupling"), dict) else {}
    video = health.get("video") if isinstance(health.get("video"), dict) else {}
    if not video:
        video = (health.get("state") or {}).get("video") or {}

    age = _f(video.get("age_s"), 99.0)
    has_frame = bool(video.get("has_frame"))
    coupling = _f(coup.get("coupling") or coup.get("coupling_ema"))
    lag_center = coup.get("lag_center_ms")
    lag = _f(lag_center if lag_center is not None else 80.0, 80.0)
    jitter = _f(coup.get("lag_jitter_ms"))
    pll = bool(coup.get("pll_lock"))
    imu = bool(coup.get("imu_bodied"))
    bind_conf = _f(coup.get("bind_conf"))
    bind_off = coup.get("bind_offset_ms")
    ghost = bool(coup.get("ghost_stick") or (health.get("ghost_stick") or {}).get("paint"))

    issues: list[str] = []
    if not has_frame or age > _STALE_AGE_S:
        issues.append("hdmi_stale")
    if not pll and coupling > 0.15:
        issues.append("pll_open")
    if lag > _LAG_WIDE_MS:
        issues.append("lag_wide")
    if jitter > _JITTER_WIDE_MS:
        issues.append("jitter_high")
    if coupling < 0.08 and imu:
        issues.append("imu_without_coupling")
    if bind_conf > 0 and bind_off is not None and abs(_f(bind_off)) > 24:
        issues.append("bind_offset")

    kind = "ok"
    if "hdmi_stale" in issues:
        kind = "warn"
    elif issues:
        kind = "note"

    return {
        "kind": kind,
        "issues": issues,
        "video_age_s": round(age, 3) if age < 90 else None,
        "has_frame": has_frame,
        "coupling": round(coupling, 3),
        "lag_center_ms": round(lag, 1),
        "lag_jitter_ms": round(jitter, 2),
        "pll_lock": pll,
        "imu_bodied": imu,
        "bind_offset_ms": bind_off,
        "bind_conf": round(bind_conf, 3),
        "ghost_stick": ghost,
        "phrase": getattr(packet, "phrase", "") or "",
    }


def run(packet: AgentPacket, *, complete=None) -> AgentReceipt | None:
    m = inspect(packet)
    issues = m["issues"] or ["none"]
    text = (
        f"sync {m['kind']} · lag {m['lag_center_ms']}ms · "
        f"pll={'lock' if m['pll_lock'] else 'open'} · "
        f"c={m['coupling']:.2f} · issues={issues}"
    )
    model = "rules"
    if complete and m["kind"] != "ok":
        extra = complete(
            "You monitor DualSense↔HDMI coupling. Observation only. "
            "No scores. No advice to cheat. One short status line.",
            json.dumps(m, default=str)[:800],
        )
        extra = (extra or "").strip().splitlines()[0] if extra else ""
        if extra:
            text = extra[:160]
            model = "reason"
    return AgentReceipt(
        role="sync_warden",
        action="audit",
        text=text,
        refs={"sync": m},
        model=model,
    )
