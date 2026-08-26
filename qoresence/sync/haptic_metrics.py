"""Private haptic corroboration metrics — logs only, no public surfaces.

Given a session's haptic JSONL plus CIVIF ticks / clip sidecars, measure
whether haptic onsets *co-occur* with existing IVC or board-lock markers.
Does not mint ``haptics_confirmed`` and does not invent outcomes.

Six-category gate (observation proxies only — never licenses):
  presence, attribution, connection_mode, temporal_join,
  board_corroboration, false_positive
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

HAPTIC_GATE_CATEGORIES = (
    "presence",
    "attribution",
    "connection_mode",
    "temporal_join",
    "board_corroboration",
    "false_positive",
)

_MENU = frozenset({"menu", "lobby", "hub", "paused", "pause"})


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


def load_clip_sidecars(clips_dir: Path | str | None) -> list[dict[str, Any]]:
    if clips_dir is None:
        return []
    root = Path(clips_dir)
    if not root.is_dir():
        if root.is_file() and root.name.endswith(".coupling.json"):
            try:
                rec = json.loads(root.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
            return [rec] if isinstance(rec, dict) else []
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.coupling.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    return float(statistics.median(xs))


def _clip01(x: float) -> float:
    return round(max(0.0, min(1.0, float(x))), 4)


def _ns(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _onset_ns(row: dict[str, Any]) -> int:
    return _ns(row.get("t_start_ns") or row.get("clock_ns"))


def _is_menuish(tick: dict[str, Any]) -> bool:
    coup = tick.get("coupling") if isinstance(tick.get("coupling"), dict) else {}
    phrase = str(coup.get("phrase") or tick.get("phrase") or "").strip().lower()
    gst = str(tick.get("game_state") or coup.get("game_state") or "").strip().lower()
    if phrase in _MENU or gst in _MENU:
        return True
    sit = tick.get("situation_snapshot") or tick.get("situation") or {}
    if isinstance(sit, dict):
        kind = str(sit.get("clutch_kind") or "").strip().lower()
        if kind in _MENU:
            return True
    return False


def _event_markers(ticks: list[dict[str, Any]], clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Known-class clocks from locked board changes / clip windows. Observation only."""
    markers: list[dict[str, Any]] = []
    prev_scores: tuple[Any, Any] | None = None
    for tick in ticks:
        clock = _ns(tick.get("clock_ns") or (tick.get("coupling") or {}).get("video_clock_ns"))
        sit = tick.get("situation_snapshot") or tick.get("situation") or {}
        sit = sit if isinstance(sit, dict) else {}
        locked = bool(tick.get("board_locked") or sit.get("board_locked"))
        home, away = sit.get("home_score"), sit.get("away_score")
        score_flip = locked and prev_scores is not None and (home, away) != prev_scores
        if locked:
            prev_scores = (home, away)
        else:
            prev_scores = None
        clutch = str(sit.get("clutch_kind") or "").strip()
        if clock <= 0:
            continue
        if score_flip:
            markers.append({"clock_ns": clock, "event_class": "score_changed", "source": "civif_tick"})
        elif locked and clutch:
            markers.append({"clock_ns": clock, "event_class": clutch, "source": "civif_tick"})
        elif locked and home is not None:
            markers.append({"clock_ns": clock, "event_class": "board_locked", "source": "civif_tick"})
    for clip in clips:
        video = clip.get("video") if isinstance(clip.get("video"), dict) else {}
        clock = _ns(video.get("t_start_ns") or clip.get("clock_ns"))
        sit = clip.get("situation") if isinstance(clip.get("situation"), dict) else {}
        kind = str(sit.get("clutch_kind") or clip.get("outcome_tag") or "").strip() or "clip_window"
        if clock:
            markers.append({"clock_ns": clock, "event_class": kind, "source": "clip_sidecar"})
    return markers


def _near(t: int, markers: list[dict[str, Any]], window_ns: int) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_dt = window_ns + 1
    for m in markers:
        dt = abs(t - int(m["clock_ns"]))
        if dt <= window_ns and dt < best_dt:
            best = m
            best_dt = dt
    return best


def corroboration_report(
    haptic: list[dict[str, Any]] | Path | str,
    *,
    civif_ticks: list[dict[str, Any]] | Path | str | None = None,
    clip_sidecars: list[dict[str, Any]] | Path | str | None = None,
    window_ms: float = 120.0,
) -> dict[str, Any]:
    """Reproducible private metrics. Claim ceiling stays co-occurrence only."""
    if isinstance(haptic, (str, Path)):
        rows = load_jsonl(haptic)
    else:
        rows = list(haptic or [])
    if isinstance(civif_ticks, (str, Path)):
        ticks = load_jsonl(civif_ticks)
    else:
        ticks = [t for t in (civif_ticks or []) if isinstance(t, dict)]
    if isinstance(clip_sidecars, (str, Path)):
        clips = load_clip_sidecars(clip_sidecars)
    else:
        clips = [c for c in (clip_sidecars or []) if isinstance(c, dict)]

    trans = [h for h in rows if h.get("kind") == "haptic_transient"]
    unav = [h for h in rows if h.get("kind") in {"haptic_unavailable", "haptic_dropout"}]
    window_ns = int(max(1.0, float(window_ms)) * 1e6)
    markers = _event_markers(ticks, clips)
    n_in_ivc = sum(1 for h in trans if (h.get("provenance") or {}).get("in_ivc_window"))
    n_coupled = sum(1 for h in trans if h.get("coupled") or (h.get("licenses") or {}).get("haptics_coupled"))
    n_observed = sum(
        1 for h in trans if (h.get("licenses") or {}).get("haptics_observed") or h.get("kind") == "haptic_transient"
    )

    n_near_board = 0
    n_near_any_marker = 0
    for h in trans:
        t = _onset_ns(h)
        if t <= 0:
            continue
        hit = _near(t, markers, window_ns)
        if hit is not None:
            n_near_any_marker += 1
            if hit.get("event_class") in {"score_changed", "board_locked"} or hit.get("source") == "civif_tick":
                n_near_board += 1

    latencies: list[float] = []
    outcome_latencies: list[float] = []
    n_fp = 0
    n_menu_fp = 0
    modes: list[str] = []
    for h in trans:
        prov = h.get("provenance") or {}
        video = prov.get("video_clock_ns")
        t = _onset_ns(h)
        if video:
            latencies.append((t - int(video)) / 1e6)
        coupling = float(prov.get("coupling") or 0.0)
        hit = _near(t, markers, window_ns) if t else None
        if hit is not None:
            outcome_latencies.append((t - int(hit["clock_ns"])) / 1e6)
        idle = (not prov.get("in_ivc_window")) and coupling < 0.1 and hit is None
        if idle:
            n_fp += 1
        mode = str(prov.get("connection_mode") or "unknown")
        modes.append(mode)

    menu_ticks = [t for t in ticks if _is_menuish(t)]
    for h in trans:
        t = _onset_ns(h)
        if t <= 0:
            continue
        if any(abs(t - _ns(mt.get("clock_ns"))) <= window_ns for mt in menu_ticks):
            n_menu_fp += 1

    n_t = len(trans)
    n_u = len(unav)
    tp = n_near_any_marker
    fp = n_fp
    fn = 0
    for m in markers:
        mc = int(m["clock_ns"])
        if not any(abs(_onset_ns(h) - mc) <= window_ns for h in trans if _onset_ns(h) > 0):
            fn += 1
    precision = (tp / (tp + fp)) if (tp + fp) else None
    recall = (tp / (tp + fn)) if (tp + fn) else None

    switches = 0
    for i in range(1, len(modes)):
        if modes[i] != modes[i - 1]:
            switches += 1
    unique_modes = sorted(set(modes))
    if len(modes) <= 1:
        mode_stability = 1.0 if modes else 0.0
    else:
        mode_stability = 1.0 - (switches / (len(modes) - 1))

    presence = n_t / max(1, n_t + n_u)
    attribution = (n_coupled / n_observed) if n_observed else 0.0
    temporal = (n_in_ivc / n_t) if n_t else 0.0
    board = (n_near_board / n_t) if n_t else 0.0
    fp_rate = ((n_fp + n_menu_fp) / n_t) if n_t else 0.0

    six = {
        "presence": _clip01(presence),
        "attribution": _clip01(attribution),
        "connection_mode": _clip01(mode_stability),
        "temporal_join": _clip01(temporal),
        "board_corroboration": _clip01(board),
        "false_positive": _clip01(1.0 - min(1.0, fp_rate)),
    }

    return {
        "n_transients": n_t,
        "n_unavailable": n_u,
        "n_in_ivc_window": int(n_in_ivc),
        "n_near_board_lock": int(n_near_board),
        "n_near_event_marker": int(n_near_any_marker),
        "n_coupled": int(n_coupled),
        "median_onset_latency_ms": _median(latencies),
        "median_outcome_latency_ms": _median(outcome_latencies),
        "false_positive_proxy": int(n_fp),
        "menu_pause_false_positive_proxy": int(n_menu_fp),
        "presence_rate": round(presence, 4),
        "attribution_accuracy": round(attribution, 4),
        "connection_modes": unique_modes,
        "connection_mode_switches": int(switches),
        "connection_mode_stability": round(mode_stability, 4),
        "precision_proxy": None if precision is None else round(precision, 4),
        "recall_proxy": None if recall is None else round(recall, 4),
        "n_event_markers": len(markers),
        "window_ms": float(window_ms),
        "six_category": six,
        "six_category_mean": round(sum(six.values()) / len(six), 4),
        "claim_ceiling": "co_occurrence_only",
        "haptics_confirmed_license": False,
        "public_surfaces": False,
    }


def session_report(
    haptic_jsonl: Path | str,
    *,
    civif_jsonl: Path | str | None = None,
    clips_dir: Path | str | None = None,
    window_ms: float = 120.0,
) -> dict[str, Any]:
    """Operator entry: paths in, private metrics out. Never writes CIVIF/Theater/MCP."""
    return corroboration_report(
        haptic_jsonl,
        civif_ticks=civif_jsonl,
        clip_sidecars=clips_dir,
        window_ms=window_ms,
    )
