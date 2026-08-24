"""CIVIF highlight + coupled-clip query. Fail-closed. Observation only."""

from __future__ import annotations

from typing import Any

from qoresence.core.civif_tick import HighlightRecord
from qoresence.foundry.index import scan_clips


def _cs(civ: dict[str, Any]) -> float | None:
    raw = civ.get("coupling_score")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _key_inputs(clip: dict[str, Any], *, bodied: bool) -> list[str]:
    if not bodied:
        return []
    names: list[str] = []
    for o in clip.get("button_onsets") or []:
        if isinstance(o, dict) and o.get("name"):
            names.append(str(o["name"]))
        if len(names) >= 8:
            break
    if names:
        return names
    bs = clip.get("buttons_summary") if isinstance(clip.get("buttons_summary"), dict) else {}
    return [str(k) for k in list(bs.keys())[:8]]


def _outcome_tag(clip: dict[str, Any], civ: dict[str, Any], *, locked: bool) -> str | None:
    if not locked:
        return None
    kind = str(civ.get("clutch_kind") or "")
    if kind:
        return kind
    for ch in clip.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        lab = str(ch.get("label") or ch.get("kind") or "").strip()
        if lab:
            return lab
    return None


def _record_from_clip(clip: dict[str, Any]) -> HighlightRecord:
    civ = clip.get("civif") if isinstance(clip.get("civif"), dict) else {}
    cs = _cs(civ)
    locked = bool(civ.get("board_locked"))
    bodied = bool(civ.get("bodied"))
    s = 0.0
    if cs is not None:
        s += cs
    if locked:
        s += 0.45
    if bodied:
        s += 0.35
    keys = _key_inputs(clip, bodied=bodied)
    tag = _outcome_tag(clip, civ, locked=locked)
    expl: dict[str, Any] = {
        "coupling_score": cs,
        "board_locked": locked,
        "controller_bodied": bodied,
        "situation_present": locked,
        "key_inputs": keys,
        "outcome_tag": tag,
        "home_score": civ.get("home_score") if locked else None,
        "away_score": civ.get("away_score") if locked else None,
    }
    stem = str(clip.get("stem") or "")
    path = clip.get("clip")
    return HighlightRecord(
        clip_id=stem,
        stem=stem,
        session_id=str(civ.get("session_id") or ""),
        coupling_score=float(cs or 0.0),
        board_locked=locked,
        controller_bodied=bodied,
        explanation=expl,
        clip_path=str(path) if path else None,
        score=s,
    )


def rank_highlights(clips_dir: Any = None, limit: int = 8) -> dict[str, Any]:
    limit = max(1, min(20, int(limit)))
    rows: list[HighlightRecord] = []
    for clip in scan_clips(clips_dir):
        rec = _record_from_clip(clip)
        if rec.score <= 0:
            continue
        rows.append(rec)
    rows.sort(key=lambda r: (-float(r.score), r.clip_id))
    hits = [r.to_dict() for r in rows[:limit]]
    try:
        from qoresence.foundry.civif_metrics import observe_highlight_scores

        observe_highlight_scores(
            [float(h.get("coupling_score") or 0) for h in hits],
            session_id=str(hits[0].get("session_id") or "") if hits else "",
        )
    except Exception:
        pass
    return {
        "ok": True,
        "count": len(hits),
        "hits": hits,
        "plane": "qoresence-observation",
        "read_only": True,
    }


def get_coupled_clips(
    session_id: str = "",
    min_coupling_score: float | None = None,
    board_locked_only: bool = False,
    controller_bodied_only: bool = False,
    situation_filters: dict[str, Any] | None = None,
    clips_dir: Any = None,
    limit: int = 20,
) -> dict[str, Any]:
    limit = max(1, min(20, int(limit)))
    filt = situation_filters if isinstance(situation_filters, dict) else {}
    clutch_min = filt.get("clutch_score_min")
    hits: list[dict[str, Any]] = []
    for clip in scan_clips(clips_dir):
        rec = _record_from_clip(clip)
        if session_id and rec.session_id != session_id:
            continue
        if min_coupling_score is not None and rec.coupling_score < float(min_coupling_score):
            continue
        if board_locked_only and not rec.board_locked:
            continue
        if controller_bodied_only and not rec.controller_bodied:
            continue
        if clutch_min is not None:
            civ = clip.get("civif") if isinstance(clip.get("civif"), dict) else {}
            stored = civ.get("clutch_score")
            try:
                if stored is None or float(stored) < float(clutch_min):
                    continue
            except (TypeError, ValueError):
                continue
        hits.append(rec.to_dict())
        if len(hits) >= limit:
            break
    return {
        "ok": True,
        "count": len(hits),
        "hits": hits,
        "plane": "qoresence-observation",
        "read_only": True,
    }
