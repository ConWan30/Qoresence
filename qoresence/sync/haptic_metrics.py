"""Private haptic corroboration metrics — logs only, no public surfaces.

Given a session's haptic JSONL plus CIVIF ticks / clip sidecars, measure
whether haptic onsets *co-occur* with existing IVC or board-lock markers.
Does not mint ``haptics_confirmed`` and does not invent outcomes.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            rows.append(rec)
    return rows


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    return float(statistics.median(xs))


def corroboration_report(
    haptic: list[dict[str, Any]] | Path | str,
    *,
    civif_ticks: list[dict[str, Any]] | None = None,
    clip_sidecars: list[dict[str, Any]] | None = None,
    window_ms: float = 120.0,
) -> dict[str, Any]:
    """Reproducible private metrics. Claim ceiling stays co-occurrence only."""
    if isinstance(haptic, (str, Path)):
        rows = load_jsonl(haptic)
    else:
        rows = list(haptic or [])
    trans = [h for h in rows if h.get("kind") == "haptic_transient"]
    unav = [h for h in rows if h.get("kind") in {"haptic_unavailable", "haptic_dropout"}]
    n_in_ivc = sum(1 for h in trans if (h.get("provenance") or {}).get("in_ivc_window"))
    window_ns = int(max(1.0, float(window_ms)) * 1e6)

    ticks = [t for t in (civif_ticks or []) if isinstance(t, dict)]
    clips = [c for c in (clip_sidecars or []) if isinstance(c, dict)]
    markers: list[int] = []
    for tick in ticks:
        if tick.get("board_locked"):
            markers.append(int(tick.get("clock_ns") or 0))
        sit = tick.get("situation_snapshot") or tick.get("situation") or {}
        if isinstance(sit, dict) and sit.get("home_score") is not None:
            markers.append(int(tick.get("clock_ns") or 0))
    for clip in clips:
        video = clip.get("video") if isinstance(clip.get("video"), dict) else {}
        clock = int(video.get("t_start_ns") or clip.get("clock_ns") or 0)
        if clock:
            markers.append(clock)
    markers = [m for m in markers if m > 0]

    n_near_board = 0
    for h in trans:
        t = int(h.get("t_start_ns") or h.get("clock_ns") or 0)
        if t <= 0:
            continue
        if any(abs(t - m) <= window_ns for m in markers):
            n_near_board += 1

    latencies: list[float] = []
    n_fp = 0
    for h in trans:
        prov = h.get("provenance") or {}
        video = prov.get("video_clock_ns")
        if video:
            latencies.append((int(h.get("t_start_ns") or 0) - int(video)) / 1e6)
        coupling = float(prov.get("coupling") or 0.0)
        if not prov.get("in_ivc_window") and coupling < 0.1:
            n_fp += 1

    n_t = len(trans)
    n_u = len(unav)
    return {
        "n_transients": n_t,
        "n_unavailable": n_u,
        "n_in_ivc_window": int(n_in_ivc),
        "n_near_board_lock": int(n_near_board),
        "median_onset_latency_ms": _median(latencies),
        "false_positive_proxy": int(n_fp),
        "presence_rate": round(n_t / max(1, n_t + n_u), 4),
        "window_ms": float(window_ms),
        "claim_ceiling": "co_occurrence_only",
        "haptics_confirmed_license": False,
        "public_surfaces": False,
    }
