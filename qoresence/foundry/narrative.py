"""CIVIF Layer 3 — fail-closed narrative over Coupled Event Records."""

from __future__ import annotations

import json
from typing import Any

from qoresence.foundry.coach import coach_from_sidecar, resolve_coupling_file


def narrative_from_sidecar(data: dict[str, Any]) -> dict[str, Any]:
    coach = coach_from_sidecar(data)
    text = " ".join(str(n) for n in (coach.get("notes") or []) if n).strip()
    return {
        "ok": True,
        "plane": "qoresence-observation",
        "text": text,
        "bodied": bool(coach.get("bodied")),
        "withheld": list(coach.get("withheld") or []),
        "situation": coach.get("situation"),
        "timing": coach.get("timing"),
        "pattern": coach.get("pattern"),
    }


def narrate_clip(clip: str, clips_dir: str | None = None) -> dict[str, Any]:
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
    out = narrative_from_sidecar(data)
    out["clip"] = str(path)
    return out
