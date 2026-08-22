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
    lock_tl = score_lock_timeline(samples, events)
    climax = climax_chapters(samples, events, clips)
    all_freezes = freeze_classified(samples, limit=None)
    freezes = all_freezes[:40]
    by_kind = _freeze_kind_counts(all_freezes)
    excluding_deck = int(sum(v for k, v in by_kind.items() if k != "deck_lock"))
    amb_n = sum(1 for rec in samples if rec.get("nameplate_ambiguous"))
    out = {
        "metrics_schema_version": 2,
        "duration_s": round(duration_s, 1),
        "samples": len(samples),
        "freeze_events": freeze_events,
        "freeze_events_by_kind": by_kind,
        "freeze_events_excluding_deck_lock": excluding_deck,
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
        "score_lock_timeline": lock_tl,
        "climax_chapters": climax,
        "freeze_classified": freezes,
        "nameplate_ambiguous_n": amb_n,
    }
    out["summary_metrics"] = {
        k: out[k]
        for k in (
            "metrics_schema_version",
            "duration_s",
            "samples",
            "freeze_events",
            "freeze_events_by_kind",
            "freeze_events_excluding_deck_lock",
            "no_frame_events",
            "score_deltas",
            "score_lock_true_ratio",
            "new_clips",
            "producer_or_ghost_cuts",
            "society_receipts",
            "deck_unreachable_samples",
        )
    }
    return out


def score_lock_timeline(
    samples: list[dict[str, Any]],
    events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Ordered lock/score transitions a stranger can audit without the JSONL."""
    rows: list[dict[str, Any]] = []
    prev: tuple[int, int] | None = None
    prev_lock: bool | None = None
    for rec in samples:
        ts = rec.get("ts") or rec.get("clock_ns")
        pair = None
        try:
            if rec.get("score_home") is not None and rec.get("score_away") is not None:
                pair = (int(rec["score_home"]), int(rec["score_away"]))
        except (TypeError, ValueError):
            pair = None
        locked = rec.get("score_vlm_locked")
        if locked is None:
            locked = rec.get("scoreboard_locked")
        src = "sample"
        if rec.get("flags") and "SCORE_DELTA" in [str(x) for x in rec.get("flags") or []]:
            src = "score_delta"
        if pair is not None and pair != prev:
            rows.append(
                {
                    "ts": ts,
                    "old": list(prev) if prev else None,
                    "new": list(pair),
                    "vlm_locked": bool(locked),
                    "source": src,
                }
            )
            prev = pair
        elif locked is not None and bool(locked) != prev_lock and pair is not None:
            rows.append(
                {
                    "ts": ts,
                    "old": list(pair),
                    "new": list(pair),
                    "vlm_locked": bool(locked),
                    "source": "lock_flip",
                }
            )
        if locked is not None:
            prev_lock = bool(locked)
    for e in events or []:
        if e.get("kind") != "SCORE_DELTA":
            continue
        cur = e.get("cur")
        old = e.get("prev")
        if cur is None:
            continue
        line = {
            "ts": e.get("ts"),
            "old": list(old) if old else None,
            "new": list(cur) if cur else None,
            "vlm_locked": True,
            "source": "event",
        }
        if line not in rows:
            rows.append(line)
    return rows[:80]


def _play_label(old: Any, new: Any) -> str:
    try:
        o0, o1 = int(old[0]), int(old[1])
        n0, n1 = int(new[0]), int(new[1])
    except (TypeError, ValueError, IndexError):
        return "score_play"
    d = max(n0 - o0, n1 - o1)
    if d >= 6:
        return "touchdown"
    if d == 3:
        return "field_goal"
    if d == 2:
        return "safety"
    if d == 1:
        return "score_play"
    if d < 0:
        return "rollback"
    return "score_play"


def climax_chapters(
    samples: list[dict[str, Any]],
    events: list[dict[str, Any]] | None = None,
    clips: list[str] | None = None,
    *,
    top_n: int = 8,
) -> list[dict[str, Any]]:
    """Ranked match peaks. Confirmed score-plays beat t0 board dumps."""
    chapters: list[dict[str, Any]] = []
    t0 = None
    if samples:
        t0 = samples[0].get("clock_ns") or samples[0].get("ts")
    for rec in samples:
        flags = [str(x) for x in (rec.get("flags") or [])]
        if "SCORE_DELTA" not in flags:
            continue
        old = rec.get("score_prev")
        new = (rec.get("score_home"), rec.get("score_away"))
        label = _play_label(old, new)
        rollback = label == "rollback" or "SCORE_ROLLBACK" in flags
        clock = rec.get("clock_ns")
        t_s = 0.0
        try:
            if t0 is not None and clock is not None:
                t_s = max(0.0, (int(clock) - int(t0)) / 1e9)
        except (TypeError, ValueError):
            t_s = 0.0
        score = 0.15 if t_s < 1.5 else 0.4
        if label in {"touchdown", "field_goal", "safety"}:
            score = 0.95
        if rollback:
            score = 0.05
        chapters.append(
            {
                "label": label,
                "t0": round(t_s, 3),
                "climax_score": score,
                "source": "confirm" if score >= 0.9 else "board",
                "stale_after_rollback": rollback,
                "ts": rec.get("ts"),
            }
        )
    for e in events or []:
        if e.get("kind") != "SCORE_DELTA":
            continue
        label = _play_label(e.get("prev"), e.get("cur"))
        if e.get("rollback"):
            label = "rollback"
        score = 0.95 if label in {"touchdown", "field_goal", "safety"} else 0.35
        if label == "rollback":
            score = 0.05
        chapters.append(
            {
                "label": label,
                "t0": 0.0,
                "climax_score": score,
                "source": "confirm" if score >= 0.9 else "event",
                "stale_after_rollback": label == "rollback",
                "ts": e.get("ts"),
            }
        )
    for p in clips or []:
        name = Path(p).name.lower()
        if "hdmi" in name or "reel" in name or "_cut" in name:
            chapters.append(
                {
                    "label": "clip_export",
                    "t0": 0.0,
                    "climax_score": 0.45,
                    "source": "export",
                    "stale_after_rollback": False,
                    "ts": None,
                    "path": p,
                }
            )
    chapters.sort(key=lambda c: (-float(c.get("climax_score") or 0), float(c.get("t0") or 0)))
    return chapters[: max(1, int(top_n))]


def _freeze_kind_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"card_stall": 0, "graph_stall": 0, "deck_lock": 0, "unknown": 0}
    for r in rows:
        kind = r.get("kind")
        if kind not in counts:
            kind = "unknown"
        counts[str(kind)] += 1
    return counts


def freeze_classified(
    samples: list[dict[str, Any]],
    *,
    limit: int | None = 40,
) -> list[dict[str, Any]]:
    from qoresence.pilot.metrics import classify_freeze, freeze_owner

    out: list[dict[str, Any]] = []
    prev_frames = None
    in_storm = False
    for rec in samples:
        flags = [str(x) for x in (rec.get("flags") or [])]
        frames = rec.get("frames")
        if "FREEZE" not in flags:
            in_storm = False
            prev_frames = frames
            continue
        if in_storm:
            prev_frames = frames
            continue
        in_storm = True
        kind = rec.get("freeze_kind")
        if kind not in {"card_stall", "graph_stall", "deck_lock", "unknown"}:
            kind = classify_freeze(
                has_frame=rec.get("has_frame"),
                age_s=rec.get("video_age_s"),
                frames=frames,
                prev_frames=prev_frames,
                graph_stall="GRAPH_STALL" in flags,
                deck_down="DECK_DOWN" in flags,
                health_err=bool(rec.get("err")),
            )
        out.append(
            {
                "ts": rec.get("ts"),
                "kind": kind,
                "age_s": rec.get("video_age_s"),
                "suspected_owner": freeze_owner(str(kind)),
            }
        )
        prev_frames = frames
    if limit is None:
        return out
    return out[: max(0, int(limit))]


def _fmt_lock_tl(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- (none)"
    lines = []
    for r in rows[:20]:
        lines.append(
            f"- `{r.get('ts')}` {r.get('old')}→{r.get('new')} locked={r.get('vlm_locked')} src={r.get('source')}"
        )
    return "\n".join(lines)


def _fmt_climax(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- (none)"
    lines = []
    for r in rows[:12]:
        lines.append(
            f"- {r.get('label')} score={r.get('climax_score')} t0={r.get('t0')} src={r.get('source')}"
        )
    return "\n".join(lines)


def _fmt_freeze(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- (none)"
    lines = []
    for r in rows[:12]:
        lines.append(
            f"- `{r.get('ts')}` kind={r.get('kind')} age_s={r.get('age_s')} owner={r.get('suspected_owner')}"
        )
    return "\n".join(lines)


def render_markdown(
    summary: dict[str, Any], *, session_jsonl: str = "", events_jsonl: str = ""
) -> str:
    freeze_n = int(summary.get("freeze_events") or 0)
    by_kind = summary.get("freeze_events_by_kind") or {}
    excluding = summary.get("freeze_events_excluding_deck_lock")
    if excluding is None:
        excluding = freeze_n
    kind_line = (
        f"card_stall={int(by_kind.get('card_stall') or 0)} "
        f"graph_stall={int(by_kind.get('graph_stall') or 0)} "
        f"deck_lock={int(by_kind.get('deck_lock') or 0)} "
        f"unknown={int(by_kind.get('unknown') or 0)}"
    )
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
| **Freeze excluding deck_lock** | {excluding} |
| **Freeze by kind** | {kind_line} |
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
- By kind: {kind_line}
- Excluding deck_lock: {excluding}

## Score lock

- Deltas (`t old→new`):
{delta_block}

## Score lock timeline

{_fmt_lock_tl(summary.get("score_lock_timeline") or [])}

## Climax chapters

{_fmt_climax(summary.get("climax_chapters") or [])}

## FREEZE classified

- schema v2 · excluding deck_lock: {excluding}
- by kind: {kind_line}
{_fmt_freeze(summary.get("freeze_classified") or [])}

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
