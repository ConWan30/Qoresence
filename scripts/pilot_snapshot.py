#!/usr/bin/env python3
"""Snapshot Deck health + timeline for pilot notes (soft-fail if server down)."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8765"
OUT_DIR = REPO_ROOT / "logs" / "pilot"


def _get(path: str, timeout: float = 3.0) -> dict | None:
    url = f"{BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
        print(f"  skip {path}: {e}")
        return None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out: dict = {
        "captured_at": ts,
        "base": BASE,
        "health": None,
        "timeline": None,
    }
    print(f"pilot_snapshot → {BASE}")
    health = _get("/health")
    out["health"] = health
    timeline = _get("/api/timeline")
    out["timeline"] = timeline

    path = OUT_DIR / f"pilot_{ts}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"  wrote {path}")

    if health is None:
        print("  note: Deck not up — start with --play --deck first")
        return 0  # soft fail

    video = (health.get("state") or {}).get("video") or {}
    print(f"  has_frame={video.get('has_frame')} target_fps={video.get('target_fps')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
