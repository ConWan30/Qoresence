"""Immutable research sidecar for title-presence observations.

Linked only. Never mutates the optical record. Default unused unless
title-presence + local learning are both on.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from qoresence.vision.title_presence import PLANE, record_valid, source_hash

KIND = "title_presence_ingredient"
DEFAULT_HALF_LIFE_S = 3600.0


def make_ingredient(
    rec: dict[str, Any],
    *,
    created_ns: int,
    half_life_s: float = DEFAULT_HALF_LIFE_S,
) -> dict[str, Any] | None:
    if not record_valid(rec):
        return None
    return {
        "kind": KIND,
        "source_plane": PLANE,
        "source_hash": source_hash(rec),
        "linked_clock_ns": rec.get("clock_ns"),
        "claim": bool(rec.get("claim")),
        "confidence_at_link": float(rec.get("confidence") or 0.0),
        "half_life_s": float(half_life_s),
        "created_ns": int(created_ns),
    }


def decayed_confidence(ingredient: dict[str, Any], now_ns: int) -> float:
    base = float(ingredient.get("confidence_at_link") or 0.0)
    half = float(ingredient.get("half_life_s") or DEFAULT_HALF_LIFE_S)
    if half <= 0:
        return 0.0
    created = int(ingredient.get("created_ns") or 0)
    age_s = max(0.0, (int(now_ns) - created) / 1e9)
    return base * math.pow(0.5, age_s / half)


def append_ingredient(path: Path, ingredient: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ingredient, sort_keys=True) + "\n")
