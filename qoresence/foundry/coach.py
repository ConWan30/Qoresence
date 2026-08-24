"""CIVIF Layer 2 — observation coaches over Coupled Event Records.

Timing and pattern coaches fail closed unless DualSense is bodied on this host.
No invented scores. No bus emit. No clip writes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from qoresence.core.coupled_event import (
    event_clock_ns,
    input_events,
    summarize_coupling_for_index,
    validate_coupling,
)

DEFAULT_CLIPS_DIR = Path("clips")


def _clips_dir(clips_dir: Path | str | None = None) -> Path:
    if clips_dir is not None:
        return Path(clips_dir)
    return Path(os.getenv("QORESENCE_CLIPS_DIR") or str(DEFAULT_CLIPS_DIR))


def resolve_coupling_file(clip: str, clips_dir: Path | str | None = None) -> Path | None:
    raw = (clip or "").strip()
    if not raw:
        return None
    d = _clips_dir(clips_dir).resolve()
    p = Path(raw)
    if p.is_file() and p.name.endswith(".coupling.json"):
        return p.resolve()
    stem = p.name
    if stem.endswith(".coupling.json"):
        stem = stem[: -len(".coupling.json")]
    elif stem.endswith(".mp4"):
        stem = Path(stem).stem
    elif stem.endswith(".coupling"):
        stem = stem[: -len(".coupling")]
    cand = (d / f"{stem}.coupling.json").resolve()
    try:
        cand.relative_to(d)
    except ValueError:
        return None
    return cand if cand.is_file() else None


def _event_label(ev: dict[str, Any]) -> str:
    for key in ("name", "button", "kind"):
        val = ev.get(key)
        if val:
            return str(val)
    return ""


def coach_from_sidecar(data: dict[str, Any]) -> dict[str, Any]:
    """Return observation notes. Timing/pattern are None when pad is not bodied."""
    card = summarize_coupling_for_index(data)
    errs = validate_coupling(data) if isinstance(data, dict) else ["sidecar is not an object"]
    withheld: list[str] = []
    notes: list[str] = []
    timing: dict[str, Any] | None = None
    pattern: dict[str, Any] | None = None
    situation: dict[str, Any] | None = None

    if not card.get("bodied"):
        withheld.extend(["timing", "pattern"])
        reason = str(card.get("reason") or "pad_not_on_this_host")
        notes.append(
            "DualSense is not bodied on this host — timing and pattern coaches withheld "
            f"({reason}). Pad stays on the console."
        )
    else:
        events = input_events(data)
        clocks = [event_clock_ns(e) for e in events]
        labels = [_event_label(e) for e in events]
        labels = [x for x in labels if x]
        intervals_ms = []
        for i in range(1, len(clocks)):
            a, b = clocks[i - 1], clocks[i]
            if a > 0 and b >= a:
                intervals_ms.append(round((b - a) / 1e6, 3))
        timing = {
            "event_count": len(events),
            "t_start_ns": clocks[0] if clocks else None,
            "t_end_ns": clocks[-1] if clocks else None,
            "intervals_ms": intervals_ms,
        }
        pattern = {
            "sequence": labels,
            "unique": sorted(set(labels)),
        }
        notes.append(f"Observed {len(events)} bodied input event(s) in the clip window.")

    if card.get("board_locked") and card.get("home_score") is not None:
        situation = {
            "board_locked": True,
            "home_score": card.get("home_score"),
            "away_score": card.get("away_score"),
        }
        notes.append(
            f"Observed locked score {card.get('home_score')}-{card.get('away_score')}."
        )
    else:
        withheld.append("score")
        notes.append("Score digits withheld — board is not locked.")

    return {
        "ok": True,
        "plane": "qoresence-observation",
        "schema_version": card.get("schema_version") or "",
        "bodied": bool(card.get("bodied")),
        "reason": str(card.get("reason") or ""),
        "withheld": withheld,
        "timing": timing,
        "pattern": pattern,
        "situation": situation,
        "coupling_score": card.get("coupling_score"),
        "notes": notes,
        "validate": errs,
    }


def coach_clip(clip: str, clips_dir: Path | str | None = None) -> dict[str, Any]:
    path = resolve_coupling_file(clip, clips_dir=clips_dir)
    if path is None:
        return {
            "ok": False,
            "error": "sidecar_not_found",
            "hint": "pass a clip stem or *.coupling.json path under clips/",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": "sidecar_unreadable", "hint": str(e)}
    if not isinstance(data, dict):
        return {"ok": False, "error": "sidecar_invalid", "hint": "not an object"}
    out = coach_from_sidecar(data)
    out["clip"] = str(path)
    return out
