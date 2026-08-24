"""CIVIF highlight query over Coupled Event Records (clips). Fail-closed."""

from __future__ import annotations

from typing import Any

from qoresence.foundry.index import scan_clips


def rank_highlights(clips_dir: Any = None, limit: int = 8) -> dict[str, Any]:
    limit = max(1, min(20, int(limit)))
    scored: list[tuple[float, dict[str, Any], list[str]]] = []
    for clip in scan_clips(clips_dir):
        civ = clip.get("civif") if isinstance(clip.get("civif"), dict) else {}
        why: list[str] = []
        s = 0.0
        cs = civ.get("coupling_score")
        try:
            if cs is not None:
                s += float(cs)
                why.append("coupling")
        except (TypeError, ValueError):
            pass
        if civ.get("board_locked"):
            s += 0.45
            why.append("board_locked")
        if civ.get("bodied"):
            s += 0.35
            why.append("bodied_input")
        if s <= 0:
            continue
        scored.append((s, clip, why))
    scored.sort(key=lambda x: (-x[0], -float(x[1].get("mtime") or 0)))
    hits = []
    for score, clip, why in scored[:limit]:
        civ = clip.get("civif") if isinstance(clip.get("civif"), dict) else {}
        hits.append(
            {
                "clip": clip.get("clip"),
                "stem": clip.get("stem"),
                "score": round(float(score), 3),
                "why": why,
                "civif": {
                    "bodied": bool(civ.get("bodied")),
                    "board_locked": bool(civ.get("board_locked")),
                    "coupling_score": civ.get("coupling_score"),
                    "home_score": civ.get("home_score"),
                    "away_score": civ.get("away_score"),
                },
            }
        )
    return {"ok": True, "count": len(hits), "hits": hits, "plane": "qoresence-observation"}
