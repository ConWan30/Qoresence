"""CIVIF Layer 3 — local JSONL dataset of coupling sidecars (observation only)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from qoresence.core.coupled_event import summarize_coupling_for_index

DEFAULT_CLIPS_DIR = Path("clips")


def _clips_dir(clips_dir: Path | str | None = None) -> Path:
    if clips_dir is not None:
        return Path(clips_dir)
    return Path(os.getenv("QORESENCE_CLIPS_DIR") or str(DEFAULT_CLIPS_DIR))


def iter_coupling_records(clips_dir: Path | str | None = None) -> Iterator[dict[str, Any]]:
    d = _clips_dir(clips_dir)
    if not d.is_dir():
        return
    for path in sorted(d.glob("*.coupling.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        card = summarize_coupling_for_index(data)
        stem = path.name[: -len(".coupling.json")] if path.name.endswith(".coupling.json") else path.stem
        yield {
            "stem": stem,
            "path": str(path),
            **card,
        }


def write_dataset(dest: Path | str, clips_dir: Path | str | None = None) -> dict[str, Any]:
    out = Path(dest)
    n = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for row in iter_coupling_records(clips_dir):
            fh.write(json.dumps(row, default=str) + "\n")
            n += 1
    return {"ok": True, "count": n, "path": str(out)}
