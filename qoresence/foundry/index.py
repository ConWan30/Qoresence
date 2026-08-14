"""FoundryIndex - local search over clips + timeline + DriveGraph (no new deps)."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
DEFAULT_CLIPS_DIR = Path("clips")
CONFIRM_KINDS = frozenset(
    {"confirm", "confirm_chat", "confirm_clip", "confirm_score", "prediction_resolve"}
)
FAST_KINDS = frozenset({"fast_chat", "fast_clip", "arm", "prediction_open"})


def _clips_dir():
    return Path(os.getenv("QORESENCE_CLIPS_DIR") or str(DEFAULT_CLIPS_DIR))


def _tokenize(s):
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t and len(t) > 1}


def _load_json(path):
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.debug("load %s: %s", path, e)
    return None


def scan_clips(clips_dir=None):
    d = Path(clips_dir) if clips_dir is not None else _clips_dir()
    out = []
    try:
        if not d.exists():
            return out
        for mp4 in sorted(d.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
            stem = mp4.stem
            ch = _load_json(d / (stem + ".chapters.json")) or {}
            bt = _load_json(d / (stem + ".buttons.json")) or {}
            buttons_summary = {}
            if isinstance(bt, dict):
                if isinstance(bt.get("buttons_summary"), dict):
                    buttons_summary = bt["buttons_summary"]
                elif isinstance(bt.get("buttons"), dict):
                    buttons_summary = bt["buttons"]
                elif isinstance(bt.get("events"), list):
                    for e in bt.get("events", []):
                        if isinstance(e, dict) and e.get("name"):
                            buttons_summary[str(e["name"])] = (
                                buttons_summary.get(str(e["name"]), 0) + 1
                            )
            if not buttons_summary and isinstance(ch.get("buttons"), dict):
                buttons_summary = ch["buttons"]
            button_onsets = button_onsets_from_sidecar(bt if isinstance(bt, dict) else None)
            chapters = ch.get("chapters") if isinstance(ch.get("chapters"), list) else []
            why = ch.get("why") if isinstance(ch.get("why"), dict) else None
            gs = ch.get("graph_summary") if isinstance(ch.get("graph_summary"), dict) else None
            try:
                st = mp4.stat()
                mtime = float(st.st_mtime)
                size = int(st.st_size)
            except Exception:
                mtime = 0.0
                size = 0
            out.append(
                {
                    "clip": str(mp4).replace("\\", "/"),
                    "stem": stem,
                    "mtime": mtime,
                    "size_bytes": size,
                    "chapters": chapters if isinstance(chapters, list) else [],
                    "buttons_summary": buttons_summary,
                    "button_onsets": button_onsets,
                    "why": why,
                    "graph_summary": gs,
                }
            )
    except Exception as e:
        log.debug("scan_clips: %s", e)
    return out


def _clip_search_text(chapters, buttons_summary, why, gs):
    parts = []
    for c in chapters[:12]:
        parts.append(str(c.get("label") or ""))
        parts.append(str(c.get("kind") or ""))
        parts.append(str(c.get("path") or ""))
    if buttons_summary:
        parts.extend(list(buttons_summary.keys()))
    if why:
        parts.append(str(why.get("line") or ""))
        parts.append(str(why.get("phase") or ""))
    if gs:
        cl = gs.get("climax") if isinstance(gs.get("climax"), dict) else {}
        parts.append(str(gs.get("phase") or ""))
        if isinstance(cl, dict):
            parts.append(str(cl.get("best_label") or ""))
        parts.append(str(gs.get("drive_id") or ""))
    return " ".join(parts).lower()


def _score_clip(qtok, clip, now_s):
    chapters = clip.get("chapters") or []
    buttons_summary = clip.get("buttons_summary") or {}
    why = clip.get("why")
    gs = clip.get("graph_summary")
    blob = _clip_search_text(chapters, buttons_summary, why, gs) or ""
    if not blob.strip():
        blob = clip.get("stem", "").lower().replace("_", " ")
    bt = _tokenize(blob)
    if not qtok:
        overlap = 1.0
    else:
        overlap = float(len(qtok & bt))
        if overlap == 0:
            q = " ".join(sorted(qtok))
            if q and q in blob:
                overlap = 0.5
    if overlap == 0 and qtok:
        return 0.0, None
    best = None
    best_bonus = 0.0
    for c in chapters:
        k = str(c.get("kind") or "")
        b = 0.0
        if k in CONFIRM_KINDS or k.startswith("confirm"):
            b += 0.7
        elif k in FAST_KINDS or k.startswith("fast"):
            b += 0.2
        if c.get("frame_seq") is not None:
            b += 0.05
        if b > best_bonus:
            best_bonus = b
            best = c
    if best is None and chapters:
        best = chapters[0]
    score = overlap + best_bonus
    try:
        cs = [float(c.get("coupling")) for c in chapters if c.get("coupling") is not None]
        if cs:
            score += max(cs) * 0.5
    except Exception:
        pass
    if gs and isinstance(gs.get("climax"), dict):
        if gs["climax"].get("has_fast_confirm"):
            score += 0.3
    mtime = float(clip.get("mtime") or 0)
    if mtime > 0 and now_s > 0:
        score += 1.0 / (1.0 + max(0.0, now_s - mtime) / 300.0)
    return score, best


def search_clips(
    query="", limit=8, since_clock_ns=0, kinds="", coupling_min=0.0, drive_id=None, clips_dir=None
):
    limit = max(1, min(20, int(limit)))
    coupling_min = max(0.0, min(1.0, float(coupling_min) if coupling_min else 0.0))
    qtok = _tokenize(query or "")
    want_kinds = {k.strip() for k in (kinds or "").split(",") if k.strip()} if kinds else None
    clips = scan_clips(clips_dir)
    now_s = time.time()
    scored = []
    for clip in clips:
        if drive_id:
            gs = clip.get("graph_summary") or {}
            cd = str(gs.get("drive_id") or "")
            if (
                cd != drive_id
                and drive_id not in clip.get("clip", "")
                and drive_id not in clip.get("stem", "")
            ):
                continue
        if coupling_min > 0:
            cs = []
            for c in clip.get("chapters") or []:
                try:
                    if c.get("coupling") is not None:
                        cs.append(float(c["coupling"]))
                except Exception:
                    continue
            if cs and max(cs) < coupling_min:
                continue
        if want_kinds:
            ch_kinds = {str(c.get("kind") or "") for c in (clip.get("chapters") or [])}
            if not (ch_kinds & want_kinds):
                continue
        score, best = _score_clip(qtok, clip, now_s)
        if score <= 0:
            continue
        scored.append((score, clip, best))
    scored.sort(key=lambda x: (-x[0], -float(x[1].get("mtime") or 0)))
    hits = []
    for score, clip, best in scored[:limit]:
        chapters = clip.get("chapters") or []
        t_s = None
        kind = ""
        label = ""
        if best:
            t_s = best.get("t_s")
            kind = str(best.get("kind") or "")
            label = str(best.get("label") or "")
        hits.append(
            {
                "clip": clip.get("clip"),
                "t_s": t_s,
                "label": label,
                "kind": kind,
                "buttons_summary": clip.get("buttons_summary") or {},
                "drive_id": (clip.get("graph_summary") or {}).get("drive_id")
                if isinstance(clip.get("graph_summary"), dict)
                else None,
                "graph": clip.get("graph_summary"),
                "why": clip.get("why"),
                "score": round(float(score), 3),
                "chapters": chapters[:3],
            }
        )
    if not hits:
        try:
            from qoresence.agents.session_timeline import get_session_timeline

            tl = get_session_timeline()
            events = tl.recent(80) if hasattr(tl, "recent") else []
            filt = []
            for ev in events:
                d = (
                    ev.to_dict()
                    if hasattr(ev, "to_dict")
                    else dict(ev)
                    if isinstance(ev, dict)
                    else {}
                )
                blob = f"{d.get('message', '')} {d.get('reason', '')} {d.get('kind', '')} {d.get('path', '')}".lower()
                bt2 = _tokenize(blob)
                if not qtok or (qtok & bt2):
                    filt.append(d)
            filt = filt[-limit:]
            for d in filt:
                if want_kinds and str(d.get("kind") or "") not in want_kinds:
                    continue
                if coupling_min and d.get("coupling") is not None:
                    try:
                        if float(d["coupling"]) < coupling_min:
                            continue
                    except Exception:
                        pass
                if drive_id and str(d.get("drive_id") or "") != drive_id:
                    continue
                if since_clock_ns and int(d.get("clock_ns") or 0) <= int(since_clock_ns):
                    continue
                hits.append(
                    {
                        "clip": None,
                        "label": str(d.get("message") or d.get("reason") or d.get("kind") or ""),
                        "kind": str(d.get("kind") or ""),
                        "buttons_summary": {},
                        "drive_id": d.get("drive_id"),
                        "graph": None,
                        "why": None,
                        "score": 0.5,
                        "chapters": [],
                        "timeline_event": d,
                    }
                )
            hits = hits[:limit]
        except Exception as e:
            log.debug("timeline fallback: %s", e)
    return {"ok": True, "count": len(hits), "hits": hits, "query": query, "limit": limit}


def get_drive_graph(drive_id=None, include_nodes=True, max_nodes=40):
    include_nodes = bool(include_nodes)
    max_nodes = max(1, min(200, int(max_nodes)))
    try:
        from qoresence.agents.drive_graph import DriveGraph, active_drive_graph
        from qoresence.agents.session_timeline import get_session_timeline

        tl = get_session_timeline()
        g = None
        did = (drive_id or "").strip()
        if not did or did.lower() == "active":
            g = active_drive_graph(tl)
        else:
            drives = tl.drives() if hasattr(tl, "drives") else []
            target = None
            for d in drives:
                try:
                    td = d.to_dict() if hasattr(d, "to_dict") else {}
                    if getattr(d, "drive_id", "") == did or td.get("drive_id") == did:
                        target = d
                        break
                except Exception:
                    continue
            if target is not None:
                g = DriveGraph.from_timeline_drive(tl, target)
            else:
                events = [
                    e
                    for e in (tl.recent(200) if hasattr(tl, "recent") else [])
                    if getattr(e, "drive_id", None) == did
                    or (e.to_dict().get("drive_id") if hasattr(e, "to_dict") else None) == did
                ]
                if events:
                    g = DriveGraph.from_events(did, events)
        if g is None:
            return {
                "ok": False,
                "error": "no_drive",
                "hint": "no active drive; run --play to create drives",
            }
        d = g.to_dict(include_nodes=include_nodes)
        if include_nodes and len(d.get("nodes", [])) > max_nodes:
            d["nodes"] = d["nodes"][:max_nodes]
            d["trimmed"] = True
        d["ok"] = True
        if "why_line" not in d:
            try:
                d["why_line"] = g.why_line()
            except Exception:
                pass
        return d
    except Exception as e:
        log.debug("get_drive_graph: %s", e)
        return {"ok": False, "error": "drive_graph_failed", "hint": str(e)}


class FoundryIndex:
    def __init__(self, clips_dir=None):
        self.clips_dir = Path(clips_dir) if clips_dir is not None else _clips_dir()

    def scan(self):
        return scan_clips(self.clips_dir)

    def search(self, query="", **kw):
        return search_clips(query, clips_dir=self.clips_dir, **kw)

    def drive_graph(self, drive_id=None, **kw):
        return get_drive_graph(drive_id, **kw)

    def get_render_candidates(self, limit=3, kinds=None, **kw):
        """Return top clip chapters suitable for Ghost Cut."""
        return get_render_candidates(limit=limit, kinds=kinds, **kw)


# TEMPORAL bind window (same as EventBinder). HID must precede the chapter mark.
_HID_BIND_WINDOW_S = 0.40
_BOARD_DUMP = re.compile(r"(live\s+[—\-–].*board)|^live\s+[—\-–]\s+board|board\s+\d+\s*-\s*\d+", re.I)


def button_onsets_from_sidecar(bt: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Clip-relative press/trigger onsets from ``*.buttons.json`` (max 256)."""
    if not isinstance(bt, dict):
        return []
    raw = bt.get("events") or []
    if not isinstance(raw, list):
        return []
    clocks = [int(e.get("clock_ns") or 0) for e in raw if isinstance(e, dict)]
    clocks = [c for c in clocks if c > 0]
    t0 = min(clocks) if clocks else 0
    out: list[dict[str, Any]] = []
    for ev in raw:
        if not isinstance(ev, dict):
            continue
        kind = str(ev.get("kind") or "")
        if kind not in {"press", "trigger"}:
            continue
        name = ev.get("name")
        if not name:
            continue
        try:
            val = float(ev.get("value") if ev.get("value") is not None else 1.0)
        except (TypeError, ValueError):
            val = 1.0
        if kind == "trigger" and val <= 0.15:
            continue
        if ev.get("t_s") is not None:
            try:
                t = float(ev["t_s"])
            except (TypeError, ValueError):
                continue
        elif ev.get("clock_ns") and t0:
            t = (int(ev["clock_ns"]) - t0) / 1e9
        else:
            continue
        item: dict[str, Any] = {"t_s": round(t, 4), "name": str(name), "kind": kind}
        prec = ev.get("imu_precursor_ms")
        if prec is not None:
            try:
                item["imu_precursor_ms"] = float(prec)
            except (TypeError, ValueError):
                pass
        out.append(item)
        if len(out) >= 256:
            break
    return out


def is_board_dump(ch: dict[str, Any]) -> bool:
    """t≈0 'Live — board 7-7' lines are not the play."""
    try:
        t = float(ch.get("t_s") or 0.0)
    except (TypeError, ValueError):
        t = 0.0
    lab = str(ch.get("label") or "")
    k = str(ch.get("kind") or "")
    low = lab.lower()
    if "touchdown" in low or "score update" in low or "field goal" in low:
        return False
    if t >= 0.4:
        return False
    if _BOARD_DUMP.search(lab):
        return True
    if t < 0.2 and (k in CONFIRM_KINDS or k.startswith("confirm")):
        return True
    return False


def _hid_near_boost(t_s: float, onsets: list[dict[str, Any]]) -> float:
    """Score bump when a press/trigger sits in the TEMPORAL window before t_s."""
    best = 0.0
    for o in onsets:
        if not isinstance(o, dict):
            continue
        try:
            ot = float(o.get("t_s") or 0.0)
        except (TypeError, ValueError):
            continue
        dt = t_s - ot
        if dt < -0.05 or dt > _HID_BIND_WINDOW_S:
            continue
        s = 0.9
        prec = o.get("imu_precursor_ms")
        if prec is not None:
            try:
                if float(prec) > 0:
                    s += 0.45
            except (TypeError, ValueError):
                pass
        if s > best:
            best = s
    return best


def score_play_chapter(ch: dict[str, Any], clip: dict[str, Any] | None = None) -> float:
    """Rank a chapter by 'is this the play' — not the first chat line."""
    k = str(ch.get("kind") or "")
    try:
        t = float(ch.get("t_s") or 0.0)
    except (TypeError, ValueError):
        t = 0.0
    s = 0.0
    lab = str(ch.get("label") or "").lower()
    if k in {"score_changed", "touchdown", "clutch"} or k.startswith("confirm_score"):
        s += 2.2
    elif "touchdown" in lab or "score update" in lab or " field goal" in lab:
        s += 2.0
    elif k in CONFIRM_KINDS or k.startswith("confirm"):
        s += 0.7
    elif k in FAST_KINDS or k.startswith("fast"):
        s += 0.35
    elif k == "a2a_scene":
        s += 0.45
    if t < 0.2:
        s -= 1.3
    if is_board_dump(ch):
        s -= 2.0
    if ch.get("coupling") is not None:
        try:
            s += float(ch["coupling"]) * 0.8
        except (TypeError, ValueError):
            pass
    if clip:
        bs = clip.get("buttons_summary") or {}
        energy = 0.0
        for v in bs.values():
            try:
                energy += float(v)
            except (TypeError, ValueError):
                continue
        s += min(1.0, energy / 20.0)
        onsets = clip.get("button_onsets")
        if not isinstance(onsets, list):
            onsets = button_onsets_from_sidecar(clip)
        # t≈0 chat dumps often share the clip's first HID edge — do not let that
        # outrank a later score/TD mark.
        if t >= 0.2 or "touchdown" in lab or "score update" in lab:
            s += _hid_near_boost(t, onsets)
    return s


def pick_play_chapter(chapters: list[Any], clip: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Choose the chapter most likely to be the actual play."""
    playable = [ch for ch in (chapters or []) if isinstance(ch, dict)]
    if not playable:
        return None
    has_real = any(not is_board_dump(ch) for ch in playable)
    best = None
    best_s = -999.0
    for ch in playable:
        if has_real and is_board_dump(ch):
            continue
        s = score_play_chapter(ch, clip)
        if best is None or s > best_s:
            best = ch
            best_s = s
    return best


def get_render_candidates(clips_dir=None, limit=3, kinds=None):
    """Pick the best *play* chapters across Foundry clips for Ghost Cut."""
    want_kinds = None
    if kinds:
        want_kinds = {k.strip() for k in kinds.split(",") if k.strip()}
    clips = scan_clips(clips_dir)
    scored: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for clip in clips:
        chapters = clip.get("chapters") or []
        if not chapters:
            continue
        graph = clip.get("graph_summary") or {}
        best = None
        best_score = -999.0
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            k = str(ch.get("kind") or "")
            if want_kinds and k not in want_kinds:
                continue
            s = score_play_chapter(ch, clip)
            if want_kinds and k in want_kinds:
                s += 0.4
            if best is None or s > best_score:
                best = ch
                best_score = s
        if graph and isinstance(graph.get("climax"), dict):
            if graph["climax"].get("has_fast_confirm"):
                best_score += 0.5
        if best is not None and best_score > -1.0:
            scored.append((best_score, clip, best))
    scored.sort(key=lambda x: (-x[0], -float(x[1].get("mtime") or 0)))
    out = []
    for score, clip, ch in scored[:limit]:
        if want_kinds and str(ch.get("kind")) not in want_kinds:
            continue
        onsets = clip.get("button_onsets") or []
        try:
            t_ch = float(ch.get("t_s") or 0.0)
        except (TypeError, ValueError):
            t_ch = 0.0
        hid_near = _hid_near_boost(t_ch, onsets if isinstance(onsets, list) else [])
        bodied = 0
        if isinstance(onsets, list):
            for o in onsets:
                if isinstance(o, dict) and o.get("imu_precursor_ms") is not None:
                    try:
                        if float(o.get("imu_precursor_ms") or 0) > 0:
                            bodied += 1
                    except (TypeError, ValueError):
                        continue
        out.append(
            {
                "clip": clip.get("clip"),
                "chapter": ch,
                "score": round(float(score), 3),
                "buttons_summary": clip.get("buttons_summary") or {},
                "graph_summary": clip.get("graph_summary"),
                "hid_near": round(float(hid_near), 3),
                "bodied_onsets": bodied,
                "onset_count": len(onsets) if isinstance(onsets, list) else 0,
            }
        )
    return out
