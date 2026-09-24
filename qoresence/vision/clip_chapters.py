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


# Closed vocabulary for observation segments (Noul hud_kind / presence_token).
# Describes what was on screen — never evaluative (no clutch / highlight / best).
SEGMENT_LABELS = {
    "live_hud": "Live",
    "preplay": "Pre-play",
    "select_plate": "Play select",
    "menu": "Menu",
    "loading": "Loading",
    "no_board": "No board",
    "unknown": "Unknown",
}
SEGMENT_PRESENCE = frozenset({"idle", "join", "dense", "unknown"})
SEGMENT_MIN_S = 1.5


def build_segments_for_window(
    runs: list[Any],
    *,
    start_ns: int,
    end_ns: int,
    min_s: float = SEGMENT_MIN_S,
) -> list[dict[str, Any]]:
    """Turn ``(clock_ns, hud_kind, presence_token)`` runs into clip-relative segments.

    Runs are clipped to [start_ns, end_ns]. Runs shorter than ``min_s`` fold
    into their neighbour (menu-flicker hysteresis), then identical neighbours merge.
    """
    if end_ns <= start_ns:
        return []
    ordered = sorted(
        (int(r[0]), str(r[1]), str(r[2])) for r in (runs or []) if len(r) >= 3
    )
    raw: list[dict[str, Any]] = []
    for i, (cns, kind, presence) in enumerate(ordered):
        nxt = ordered[i + 1][0] if i + 1 < len(ordered) else end_ns
        t0 = max(cns, start_ns)
        t1 = min(nxt, end_ns)
        if t1 <= t0:
            continue
        raw.append(
            {
                "t0_s": (t0 - start_ns) / 1e9,
                "t1_s": (t1 - start_ns) / 1e9,
                "hud_kind": kind if kind in SEGMENT_LABELS else "unknown",
                "presence": presence if presence in SEGMENT_PRESENCE else "unknown",
            }
        )

    folded: list[dict[str, Any]] = []
    for seg in raw:
        short = seg["t1_s"] - seg["t0_s"] < float(min_s)
        if short and folded:
            folded[-1]["t1_s"] = seg["t1_s"]
            continue
        if folded and folded[-1].get("_short"):
            seg = dict(seg, t0_s=folded[-1]["t0_s"])
            folded.pop()
        folded.append(dict(seg, _short=short))

    out: list[dict[str, Any]] = []
    for seg in folded:
        seg.pop("_short", None)
        if (
            out
            and out[-1]["hud_kind"] == seg["hud_kind"]
            and out[-1]["presence"] == seg["presence"]
        ):
            out[-1]["t1_s"] = seg["t1_s"]
            continue
        out.append(seg)
    for seg in out:
        seg["t0_s"] = round(seg["t0_s"], 3)
        seg["t1_s"] = round(seg["t1_s"], 3)
        seg["label"] = SEGMENT_LABELS[seg["hud_kind"]]
    return out


def _noul_segments(start_ns: int, end_ns: int) -> list[dict[str, Any]]:
    """Segments from the Noul observatory; empty when it is off (fail closed)."""
    try:
        from qoresence.observability.noul_observatory import get_noul_observatory

        obs = get_noul_observatory()
        if obs is None or not getattr(obs, "enabled", False):
            return []
        return build_segments_for_window(
            obs.runs_in_window(start_ns, end_ns), start_ns=start_ns, end_ns=end_ns
        )
    except Exception as e:
        log.debug("noul segments skipped: %s", e)
        return []


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
        if (
            kind not in _CHAPTER_KINDS
            and not kind.startswith("fast_")
            and not kind.startswith("confirm")
        ):
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
    graph_summary: dict[str, Any] | None = None,
    segments: list[dict[str, Any]] | None = None,
) -> Path | None:
    """Write ``<stem>.chapters.json`` with chapters + optional buttons + why + graph."""
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
        if why is None:
            payload.pop("why", None)
        if graph_summary:
            # Trimmed: phase, climax, match_rate
            cl = graph_summary.get("climax") or {}
            payload["graph_summary"] = {
                "phase": graph_summary.get("phase"),
                "match_rate": graph_summary.get("match_rate", cl.get("match_rate")),
                "climax": {
                    "score": cl.get("score"),
                    "best_label": cl.get("best_label"),
                    "has_fast_confirm": cl.get("has_fast_confirm"),
                },
                "drive_id": graph_summary.get("drive_id"),
            }
        if segments:
            payload["segments"] = segments
            payload["segments_source"] = "noul"
            payload["licenses_digits"] = False
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("chapters sidecar: %s (%d chapters)", out.name, len(chapters))
        return out
    except Exception as e:
        log.debug("chapters sidecar write failed: %s", e)
        return None


def chapters_after_export(
    mp4_path: str | Path,
    duration_s: float,
    *,
    window_start_ns: int | None = None,
    window_end_ns: int | None = None,
) -> Path | None:
    """Convenience: pull timeline + InputRing, write chapters sidecar."""
    try:
        from qoresence.agents.session_timeline import get_session_timeline

        tl = get_session_timeline()
        # Events in last duration_s (absolute clock)
        end_ns = int(window_end_ns) if window_end_ns is not None else time.monotonic_ns()
        if window_start_ns is not None:
            start_ns = int(window_start_ns)
        else:
            start_ns = end_ns - int(max(0.5, float(duration_s)) * 1e9)
        segments = _noul_segments(start_ns, end_ns)
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
        # DriveGraph ranking: boost / merge chapter seeds (never drop confirms)
        graph_summary = None
        try:
            from qoresence.agents.drive_graph import DriveGraph, active_drive_graph

            g = active_drive_graph(tl)
            if g is None and events:
                g = DriveGraph.from_events("export", events)
            if g is not None and g.nodes:
                graph_summary = {
                    "phase": g.phase(),
                    "climax": g.climax_score(),
                    "match_rate": g.climax_score().get("match_rate", 0),
                    "drive_id": g.drive_id,
                }
                ranked = g.ranked_chapter_nodes(k=8)
                # Map ranked nodes into t_s within export window
                start_ns = end_ns - int(max(0.5, float(duration_s)) * 1e9)
                dur = max(0.5, float(duration_s))
                by_label = {(c.get("label"), round(float(c.get("t_s") or 0), 2)) for c in chapters}
                for n in ranked:
                    t_s = max(0.0, min(dur, (n.clock_ns - start_ns) / 1e9))
                    key = (n.label, round(t_s, 2))
                    if key in by_label:
                        continue
                    # Prefer graph-ranked nodes (especially confirms)
                    chapters.append(
                        {
                            "t_s": round(t_s, 3),
                            "label": n.label,
                            "kind": n.kind,
                            "path": n.path or "",
                            "frame_seq": n.frame_seq,
                            "source": "drive_graph",
                        }
                    )
                    by_label.add(key)
                chapters.sort(key=lambda c: float(c.get("t_s") or 0))
        except Exception as e:
            log.debug("drive graph chapters merge skipped: %s", e)

        why = tl.why_last() or {}
        try:
            from qoresence.sync.coupling_ticket import get_coupling_book, why_strip_coupling
            from qoresence.sync.ivc import get_last_coupling
            from qoresence.sync.play_phrase import LIVE_PHRASES
            from qoresence.vision.confirm_ticket import get_ticket_book, why_strip

            coup = get_last_coupling() or {}
            why = dict(why)
            phrase = str(coup.get("phrase") or "IDLE")
            why["phrase"] = phrase
            why["coupling_ticket_id"] = coup.get("coupling_ticket_id") or ""
            why["confirm"] = why_strip(get_ticket_book().latest())
            why["couple"] = why_strip_coupling(get_coupling_book().latest_live())
            extra = f"{why['confirm']} · {why['couple']} · phrase={phrase}"
            why["line"] = f"{why.get('line') or extra} · {extra}" if why.get("line") else extra
            if phrase in LIVE_PHRASES and why.get("coupling_ticket_id"):
                chapters.append(
                    {
                        "t_s": round(max(0.0, float(duration_s) * 0.5), 3),
                        "label": phrase,
                        "kind": "phrase",
                        "path": "fast",
                        "frame_seq": coup.get("frame_seq"),
                        "source": "coupling_ticket",
                    }
                )
                chapters.sort(key=lambda c: float(c.get("t_s") or 0))
        except Exception:
            pass
        return write_clip_sidecar(
            mp4_path,
            chapters,
            buttons=buttons_summary,
            why=why,
            duration_s=float(duration_s),
            graph_summary=graph_summary,
            segments=segments,
        )
    except Exception as e:
        log.debug("chapters_after_export failed: %s", e)
        return None
