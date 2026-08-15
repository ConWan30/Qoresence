"""Render pilot closeout JSON + markdown from a session JSONL."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


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


def summarize(
    samples: list[dict[str, Any]],
    *,
    events: list[dict[str, Any]] | None = None,
    clip_paths: list[str] | None = None,
) -> dict[str, Any]:
    events = events or []
    flags: Counter[str] = Counter()
    freeze_events = 0
    no_frame_events = 0
    deck_down = 0
    score_deltas = 0
    locked_n = 0
    scored_n = 0
    society_n = 0
    prev_freeze = False
    prev_no = False
    deltas: list[str] = []

    for rec in samples:
        fl = [str(x) for x in (rec.get("flags") or [])]
        for f in fl:
            flags[f] += 1
        if "FREEZE" in fl:
            if not prev_freeze:
                freeze_events += 1
            prev_freeze = True
        else:
            prev_freeze = False
        if "NO_FRAMES" in fl:
            if not prev_no:
                no_frame_events += 1
            prev_no = True
        else:
            prev_no = False
        if "DECK_DOWN" in fl or rec.get("err"):
            deck_down += 1
        if "SCORE_DELTA" in fl:
            score_deltas += 1
            old = rec.get("score_prev")
            new = (rec.get("score_home"), rec.get("score_away"))
            ts = str(rec.get("ts") or "")[-12:]
            deltas.append(f"{ts} {old}→{new}")
        if rec.get("score_home") is not None and rec.get("score_away") is not None:
            scored_n += 1
            if rec.get("score_vlm_locked"):
                locked_n += 1
        rec_soc = rec.get("society_receipts")
        if rec_soc is not None:
            try:
                society_n = max(society_n, int(rec_soc))
            except (TypeError, ValueError):
                pass

    if events:
        score_deltas = max(score_deltas, sum(1 for e in events if e.get("kind") == "SCORE_DELTA"))
        for e in events:
            if e.get("kind") == "SCORE_DELTA" and e.get("line"):
                if e["line"] not in deltas:
                    deltas.append(str(e["line"]))

    clips = list(clip_paths or [])
    if not clips:
        seen: set[str] = set()
        for rec in samples:
            for p in rec.get("new_clips") or []:
                s = str(p)
                if s not in seen:
                    seen.add(s)
                    clips.append(s)

    producer = [
        p
        for p in clips
        if "hdmi_clip_" in p.replace("\\", "/") or "_cut" in p or "reel_" in Path(p).name
    ]
    duration_s = 0.0
    if samples:
        duration_s = float(len(samples)) * 2.0
        try:
            # prefer first/last clock if present
            c0 = samples[0].get("clock_ns")
            c1 = samples[-1].get("clock_ns")
            if c0 and c1 and int(c1) > int(c0):
                duration_s = (int(c1) - int(c0)) / 1e9
        except (TypeError, ValueError):
            pass

    lock_ratio = (locked_n / scored_n) if scored_n else None
    top = [f"{k}:{v}" for k, v in flags.most_common(8)]
    return {
        "duration_s": round(duration_s, 1),
        "samples": len(samples),
        "freeze_events": freeze_events,
        "no_frame_events": no_frame_events,
        "score_deltas": score_deltas,
        "score_lock_true_ratio": None if lock_ratio is None else round(lock_ratio, 3),
        "new_clips": len(clips),
        "producer_or_ghost_cuts": len(producer),
        "society_receipts": society_n,
        "deck_unreachable_samples": deck_down,
        "top_flags": top,
        "score_delta_lines": deltas,
        "clip_paths": clips,
    }


def render_markdown(summary: dict[str, Any], *, session_jsonl: str = "", events_jsonl: str = "") -> str:
    freeze_n = int(summary.get("freeze_events") or 0)
    capture_ok = freeze_n == 0 and int(summary.get("no_frame_events") or 0) == 0
    soc = int(summary.get("society_receipts") or 0)
    if soc <= 0:
        soc_line = "n/a (no receipts observed)"
    elif soc < 20:
        soc_line = f"quiet · {soc} receipts"
    else:
        soc_line = f"noisy · {soc} receipts"
    clips = summary.get("clip_paths") or []
    clip_block = "\n".join(f"- `{p}`" for p in clips) if clips else "- (none)"
    deltas = summary.get("score_delta_lines") or []
    delta_block = "\n".join(f"- `{d}`" for d in deltas) if deltas else "- (none)"
    issues = summary.get("top_flags") or []
    issue_block = "\n".join(f"- {x}" for x in issues) if issues else "- (none)"
    ratio = summary.get("score_lock_true_ratio")
    ratio_s = "n/a" if ratio is None else f"{ratio:.0%}"
    return f"""# Pilot closeout

| Field | Value |
|-------|--------|
| **Duration** | {summary.get("duration_s")} s |
| **Samples** | {summary.get("samples")} |
| **Capture stable** | {"Y" if capture_ok else "N"} |
| **Freeze events** | {freeze_n} |
| **No-frame events** | {summary.get("no_frame_events")} |
| **Score deltas** | {summary.get("score_deltas")} |
| **Score lock ratio** | {ratio_s} |
| **New clips** | {summary.get("new_clips")} |
| **Producer / Ghost Cuts** | {summary.get("producer_or_ghost_cuts")} |
| **Society receipts** | {soc} |
| **Deck unreachable samples** | {summary.get("deck_unreachable_samples")} |

---

## Capture stability

- Alive? {"Y" if capture_ok else "N"}
- Freeze storms: {freeze_n}

## Score lock

- Deltas (`t old→new`):
{delta_block}

## Clips created

{clip_block}

## Society

- {soc_line}

## Top issues

{issue_block}

## Raw logs

- session: `{session_jsonl}`
- events: `{events_jsonl}`
"""


def write_closeout(
    jsonl_path: Path,
    *,
    events_path: Path | None = None,
    out_json: Path | None = None,
    out_md: Path | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    samples = _load_jsonl(jsonl_path)
    events = _load_jsonl(events_path) if events_path else []
    summary = summarize(samples, events=events)
    stamp = jsonl_path.stem.replace("session_", "")
    out_dir = jsonl_path.parent
    out_json = out_json or (out_dir / f"closeout_{stamp}.json")
    out_md = out_md or (out_dir / f"closeout_{stamp}.md")
    out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(
        render_markdown(
            summary,
            session_jsonl=str(jsonl_path),
            events_jsonl=str(events_path or ""),
        ),
        encoding="utf-8",
    )
    return out_json, out_md, summary
