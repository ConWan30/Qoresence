"""Session-end logbook debrief. Default OFF. File-plane only.

Reads events JSONL and Foundry ``*.chapters.json`` after live capture stops.
Never joins the live event bus, never takes a lobe lock, never runs on the
streamer/capture thread.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_ON = False


def is_enabled(flag: bool | None = None) -> bool:
    """Logbook stays off unless an explicit CLI/one-shot flag is True."""
    if flag is None:
        return DEFAULT_ON
    return bool(flag)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
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


def _load_chapter_files(clips_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    if not clips_dir.is_dir():
        return out
    for path in sorted(clips_dir.glob("*.chapters.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        stem = path.name.removesuffix(".chapters.json")
        out.append((stem, data))
    return out


def summarize(
    events: list[dict[str, Any]],
    chapter_files: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    kinds: Counter[str] = Counter()
    for rec in events:
        kind = str(rec.get("kind") or rec.get("type") or "")
        if kind:
            kinds[kind] += 1
    chapters: list[dict[str, Any]] = []
    stems: list[str] = []
    for stem, payload in chapter_files:
        stems.append(stem)
        for ch in payload.get("chapters") or []:
            if isinstance(ch, dict):
                chapters.append({**ch, "clip": stem})
    return {
        "event_count": len(events),
        "chapter_count": len(chapters),
        "clip_stems": stems,
        "kinds": dict(kinds),
        "chapters": chapters,
        "plane": "session_end_files",
    }


def render_markdown(payload: dict[str, Any]) -> str:
    kind_block = "\n".join(f"- {k}: {v}" for k, v in (payload.get("kinds") or {}).items()) or "- (none)"
    ch_block = (
        "\n".join(
            f"- {c.get('t_s', '?')}s {c.get('kind', '')}: {c.get('label', '')}"
            for c in (payload.get("chapters") or [])[:32]
        )
        or "- (none)"
    )
    clips = ", ".join(payload.get("clip_stems") or []) or "(none)"
    return f"""# Session logbook debrief

Events: {payload.get("event_count", 0)}
Chapters: {payload.get("chapter_count", 0)}
Clips: {clips}

## Event kinds

{kind_block}

## Chapters

{ch_block}
"""


def write_debrief(
    *,
    events_jsonl: Path,
    clips_dir: Path | None = None,
    out_md: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Write a short debrief markdown + JSON next to the session JSONL."""
    events_jsonl = Path(events_jsonl)
    clips_dir = Path(clips_dir) if clips_dir is not None else Path("clips")
    payload = summarize(_load_jsonl(events_jsonl), _load_chapter_files(clips_dir))
    out_md = Path(out_md) if out_md is not None else (events_jsonl.parent / f"logbook_{events_jsonl.stem}.md")
    out_json = out_md.with_suffix(".json")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(payload), encoding="utf-8")
    out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out_md, payload
