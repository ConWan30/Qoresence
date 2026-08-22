"""Agent Companion — observation-plane duty pack for a live gamer.

ClutchBot still autonomously clips clutch gameplay (fast coupling +
red/late, confirm on locked score change). This pack does not write
MP4s, invent scores, open capture, or emit bus events. MCP stays
read-only. Society ghost_editor remains propose-only; the operator
exports via existing ``POST /api/clip``.
"""

from __future__ import annotations

import re
from typing import Any

PLANE = "qoresence-observation"
CLIP_COUPLING = 0.55
CLIMAX_ARM = 0.65
_SCORE_PAIR = re.compile(r"\b\d{1,2}\s*[-–—:]\s*\d{1,2}\b")


def _rec(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v: Any) -> int | None:
    n = _num(v)
    if n is None:
        return None
    return int(n)


def _locked(sit: dict[str, Any]) -> bool:
    if sit.get("score_vlm_locked") or sit.get("scoreboard_locked") or sit.get("confirm_ticket_id"):
        return True
    src = str(sit.get("score_source") or sit.get("scoreboard_source") or "")
    return src in {"vlm", "ocr", "scoreboard"}


def _is_red_zone(sit: dict[str, Any]) -> bool:
    pos = str(sit.get("field_position") or sit.get("field_pos") or "").lower()
    if "red" in pos and "zone" in pos:
        return True
    if "opp" in pos:
        m = re.search(r"opp(?:onent)?\s*(\d+)", pos)
        if m and int(m.group(1)) <= 20:
            return True
    return False


def _is_close(sit: dict[str, Any]) -> bool:
    if not _locked(sit):
        return False
    h = _int(sit.get("home_score", sit.get("score_home")))
    a = _int(sit.get("away_score", sit.get("score_away")))
    if h is None or a is None:
        return False
    return abs(h - a) <= 8


def _is_late(sit: dict[str, Any]) -> bool:
    q = _int(sit.get("quarter"))
    return q is not None and q >= 4


def clip_armed(
    *,
    coupling: float,
    red: bool,
    close: bool,
    late: bool,
    climax: float,
) -> bool:
    """Same gates as FastMomentEngine clip + Glass climax/score_play worth."""
    if climax >= CLIMAX_ARM:
        return True
    return coupling >= CLIP_COUPLING and (red or (close and late))


def _last_clip(moments: list[Any], last_moment: dict[str, Any] | None) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    if last_moment:
        rows.append(last_moment)
    for m in reversed(list(moments or [])):
        if isinstance(m, dict):
            rows.append(m)
    for m in rows:
        action = str(m.get("action") or "").lower()
        title = str(m.get("title") or "")
        if action != "clip" and "clip" not in title.lower():
            continue
        path = str(m.get("moment_path") or m.get("path") or "")
        if path not in {"fast", "confirm"}:
            path = "confirm" if "confirm" in title.lower() else "fast" if "fast" in title.lower() else ""
        url = str(m.get("url") or "")
        name = str(m.get("name") or "")
        if not url and name:
            url = f"/media/clips/{name}"
        if not url:
            blob = f"{m.get('reason') or ''} {m.get('path') or ''} {name}"
            hit = re.search(r"hdmi_clip_[\w.\-]+\.(mp4|avi)", blob, flags=re.I)
            if hit:
                name = hit.group(0)
                url = f"/media/clips/{name}"
        if not url:
            continue
        return {
            "title": title[:80],
            "path": path,
            "url": url,
            "name": name,
            "reason": str(m.get("reason") or "")[:160],
        }
    return None


def _society_role(last: list[Any], role: str) -> dict[str, Any] | None:
    for row in reversed(list(last or [])):
        if not isinstance(row, dict):
            continue
        if str(row.get("role") or "") != role:
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        refs = _rec(row.get("refs"))
        return {
            "action": str(row.get("action") or "note"),
            "text": text[:400],
            "refs": refs,
            "model": str(row.get("model") or "rules"),
        }
    return None


def _sanitize_say(line: str, *, locked: bool) -> str:
    if locked:
        return line
    return _SCORE_PAIR.sub("the scoreboard", line)


def build_companion(
    *,
    situation: dict[str, Any] | None = None,
    coupling: dict[str, Any] | None = None,
    moments: list[Any] | None = None,
    last_moment: dict[str, Any] | None = None,
    society: dict[str, Any] | None = None,
    drive_graph: dict[str, Any] | None = None,
    why_last: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Duty pack for Theater. Auto-clip stays on. No invented scores."""
    sit = _rec(situation)
    coup = _rec(coupling)
    soc = _rec(society)
    graph = _rec(drive_graph)
    why = _rec(why_last)
    climax = _num(why.get("climax_score"))
    cl = _rec(graph.get("climax"))
    if climax is None:
        climax = _num(cl.get("score")) or 0.0
    else:
        climax = max(climax, _num(cl.get("score")) or 0.0)
    coupling_f = _num(coup.get("coupling")) or 0.0
    red = _is_red_zone(sit)
    close = _is_close(sit)
    late = _is_late(sit)
    armed = clip_armed(
        coupling=coupling_f, red=red, close=close, late=late, climax=float(climax or 0.0)
    )
    last = _last_clip(list(moments or []), last_moment if isinstance(last_moment, dict) else None)
    coach = _society_role(list(soc.get("last") or []), "drive_coach")
    cut_rec = _society_role(list(soc.get("last") or []), "ghost_editor")
    cut = None
    if cut_rec and cut_rec.get("action") == "propose_cut":
        refs = _rec(cut_rec.get("refs"))
        cut = {
            "stem": str(refs.get("clip") or ""),
            "t_s_in": _num(refs.get("t_s_in")),
            "t_s_out": _num(refs.get("t_s_out")),
            "title": str(refs.get("title") or cut_rec.get("text") or "")[:80],
            "text": cut_rec.get("text"),
        }
    locked = _locked(sit)
    phase = str(graph.get("phase") or why.get("phase") or "")
    match_rate = _num(graph.get("match_rate") or cl.get("match_rate"))
    why_line = str(why.get("line") or why.get("best_label") or cl.get("best_label") or "")
    may_say: list[str] = [
        "ClutchBot auto-clips clutch — fast coupling plus red or late-close, confirm on locked score change"
    ]
    if armed:
        may_say.append("clip armed")
    if last and last.get("title"):
        may_say.append(_sanitize_say(f"last clip {last['title']}", locked=locked))
    if coach and coach.get("text"):
        may_say.append(_sanitize_say(str(coach["text"]), locked=locked))
    if cut and cut.get("title"):
        may_say.append(f"ghost cut proposed {cut['title']}")
    if why_line:
        may_say.append(_sanitize_say(why_line, locked=locked))

    silence: list[str] = []
    if not locked:
        silence.append("score_not_locked")
    if not last:
        silence.append("no_clip_yet")
    if not armed:
        silence.append("clip_not_armed")

    return {
        "ok": True,
        "plane": PLANE,
        "claim_ceiling": "observation_only",
        "auto_clip": True,
        "clip": {
            "duty": "auto",
            "armed": armed,
            "last": last,
            "gates": {
                "coupling": round(coupling_f, 3),
                "red_zone": red,
                "close": close,
                "late": late,
                "climax": round(float(climax or 0.0), 3),
            },
        },
        "drive": {
            "phase": phase or None,
            "climax": round(float(climax or 0.0), 3) if climax else None,
            "match_rate": round(match_rate, 3) if match_rate is not None else None,
            "why": why_line or None,
        },
        "coach": {"text": coach["text"], "model": coach.get("model")} if coach else None,
        "cut": cut,
        "society": {
            "enabled": bool(soc.get("enabled")),
            "alive": bool(soc.get("alive")),
        },
        "may_say": may_say,
        "must_not_invent": silence,
    }


def snapshot_companion() -> dict[str, Any]:
    """Live companion from in-process glasses. Never opens capture.

    Reads DeckState fields directly — do not call ``DeckState.snapshot()``
    here (that snapshot attaches this pack).
    """
    sit: dict[str, Any] = {}
    coup: dict[str, Any] = {}
    moments: list[Any] = []
    last_moment: dict[str, Any] | None = None
    society: dict[str, Any] = {}
    drive_graph: dict[str, Any] = {}
    why_last: dict[str, Any] = {}
    try:
        from qoresence.deck import server as deck

        sit = _rec(getattr(deck._state, "situation", None))
        moments = list(getattr(deck._state, "moments", None) or [])
        lm = getattr(deck._state, "last_moment", None)
        last_moment = lm if isinstance(lm, dict) else None
    except Exception:
        pass
    try:
        from qoresence.sync.ivc import get_last_coupling

        coup = dict(get_last_coupling() or {})
    except Exception:
        coup = {}
    try:
        from qoresence.agents.society import get_society

        soc = get_society()
        society = soc.stats() if soc is not None else {"enabled": False}
    except Exception:
        society = {"enabled": False}
    if not drive_graph:
        try:
            from qoresence.agents.session_timeline import get_session_timeline

            tl = get_session_timeline().snapshot(recent_n=8)
            drive_graph = _rec(tl.get("drive_graph"))
            if not why_last:
                why_last = _rec(tl.get("why_last"))
        except Exception:
            pass
    return build_companion(
        situation=sit,
        coupling=coup,
        moments=moments,
        last_moment=last_moment,
        society=society,
        drive_graph=drive_graph,
        why_last=why_last,
    )
