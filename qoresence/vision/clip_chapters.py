"""Clip chapter sidecars from SessionTimeline + InputRing (observation plane).

Writes ``<stem>.chapters.json`` after Foundry export — never fails the MP4.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Timeline kinds that become chapter marks
_CHAPTER_KINDS = frozenset(
    {
        "fast_clip",
        "fast_chat",
        "arm",
        "confirm",
        "confirm_chat",
        "confirm_clip",
        "prediction_open",
        "prediction_resolve",
        "prediction_cancel",
    }
)


def build_chapters_for_window(
    duration_s: float,
    timeline_events: list[Any],
    input_events: list[dict[str, Any]] | None = None,
    *,
    window_end_ns: int | None = None,
) -> list[dict[str, Any]]:
    """Build ordered chapter marks in [0, duration_s] for a clip window.

    Timeline events use absolute ``clock_ns``; window ends at ``window_end_ns``
    (default now) and starts ``duration_s`` earlier.
    """
    dur = max(0.5, float(duration_s))
    end_ns = int(window_end_ns if window_end_ns is not None else time.monotonic_ns())
    start_ns = end_ns - int(dur * 1e9)
    chapters: list[dict[str, Any]] = []

    for ev in timeline_events or []:
        if hasattr(ev, "to_dict"):
            d = ev.to_dict()
        elif isinstance(ev, dict):
            d = ev
        else:
            continue
        kind = str(d.get("kind") or "")
        if kind not in _CHAPTER_KINDS and not kind.startswith("fast_") and not kind.startswith("confirm"):
            continue
        cns = int(d.get("clock_ns") or 0)
        if cns < start_ns or cns > end_ns:
            continue
        t_s = max(0.0, min(dur, (cns - start_ns) / 1e9))
        label = d.get("message") or d.get("reason") or kind
        chapters.append(
            {
                "t_s": round(t_s, 3),
                "label": str(label)[:80],
                "kind": kind,
                "path": d.get("path") or "",
                "frame_seq": d.get("frame_seq"),
            }
        )

    # Sparse timeline → add input presses as marks
    if len(chapters) < 2 and input_events:
        for ie in input_events:
            if ie.get("kind") not in ("press", "trigger"):
                continue
            cns = int(ie.get("clock_ns") or 0)
            if cns < start_ns or cns > end_ns:
                continue
            t_s = max(0.0, min(dur, (cns - start_ns) / 1e9))
            chapters.append(
                {
                    "t_s": round(t_s, 3),
                    "label": f"input {ie.get('name', '?')}",
                    "kind": "input",
                    "path": "fast",
                }
            )

    chapters.sort(key=lambda c: (float(c.get("t_s") or 0), str(c.get("kind") or "")))
    # Dedup near-identical times
    out: list[dict[str, Any]] = []
    last_t = -999.0
    for ch in chapters:
        t = float(ch["t_s"])
        if out and abs(t - last_t) < 0.05 and ch.get("kind") == out[-1].get("kind"):
            continue
        out.append(ch)
        last_t = t
    return out


def write_clip_sidecar(
    mp4_path: str | Path,
    chapters: list[dict[str, Any]],
    buttons: dict[str, Any] | list | None = None,
    why: dict[str, Any] | None = None,
    *,
    duration_s: float | None = None,
) -> Path | None:
    """Write ``<stem>.chapters.json`` with chapters + optional buttons + why."""
    try:
        path = Path(mp4_path)
        out = path.with_name(path.stem + ".chapters.json")
        payload: dict[str, Any] = {
            "duration_s": duration_s,
            "chapters": chapters,
            "why": why,
            "buttons": buttons or {},
            "source": "session_timeline",
        }
        # Drop null why
        if why is None:
            payload.pop("why", None)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("chapters sidecar: %s (%d chapters)", out.name, len(chapters))
        return out
    except Exception as e:
        log.debug("chapters sidecar write failed: %s", e)
        return None


def chapters_after_export(mp4_path: str | Path, duration_s: float) -> Path | None:
    """Convenience: pull timeline + InputRing, write chapters sidecar."""
    try:
        from qoresence.agents.session_timeline import get_session_timeline

        tl = get_session_timeline()
        # Events in last duration_s (absolute clock)
        end_ns = time.monotonic_ns()
        start_ns = end_ns - int(max(0.5, float(duration_s)) * 1e9)
        events = tl.events_in_window(start_ns, end_ns)
        if not events:
            events = tl.recent(40)

        input_events: list[dict[str, Any]] = []
        buttons_summary: dict[str, Any] = {}
        try:
            from qoresence.sync.input_ring import get_input_ring

            input_events = get_input_ring().snapshot(seconds=float(duration_s))
            for e in input_events:
                if e.get("kind") in ("press", "trigger") and e.get("name"):
                    n = str(e["name"])
                    buttons_summary[n] = buttons_summary.get(n, 0) + 1
        except Exception:
            pass

        chapters = build_chapters_for_window(
            float(duration_s),
            events,
            input_events,
            window_end_ns=end_ns,
        )
        why = tl.why_last()
        return write_clip_sidecar(
            mp4_path,
            chapters,
            buttons=buttons_summary,
            why=why,
            duration_s=float(duration_s),
        )
    except Exception as e:
        log.debug("chapters_after_export failed: %s", e)
        return None
