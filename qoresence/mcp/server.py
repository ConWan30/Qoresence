"""Qoresence MCP — Glass D (stdio fallback)."""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
SERVER_NAME = "qoresence"
SERVER_VERSION = "0.1.0-dev"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TOKEN_FILE = ".secrets/agent_glass.token"

# Lazy FastMCP handle — never imported unless QORESENCE_MCP_USE_FASTMCP=1
_mcp_fastmcp: Any = None


def _get_fastmcp():
    """Return a configured FastMCP instance, lazily loaded."""
    global _mcp_fastmcp
    if _mcp_fastmcp is not None:
        return _mcp_fastmcp
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        return None
    mcp = FastMCP(SERVER_NAME)

    @mcp.tool()  # type: ignore
    def get_snapshot() -> dict:  # type: ignore
        return handle_get_snapshot()

    @mcp.tool()  # type: ignore
    def get_events(since: int = 0, types: str = "", limit: int = 20) -> dict:  # type: ignore
        return handle_get_events(since=since, types=types, limit=limit)

    @mcp.tool()  # type: ignore
    def get_health() -> dict:  # type: ignore
        return handle_get_health()

    @mcp.tool()  # type: ignore
    def get_frame() -> dict:  # type: ignore
        return handle_get_frame()

    @mcp.tool()  # type: ignore
    def search_clips(
        query: str = "",
        limit: int = 8,
        kinds: str = "",
        coupling_min: float = 0.0,
        drive_id: str = "",
        since_clock_ns: int = 0,
    ) -> dict:  # type: ignore
        return handle_search_clips(
            query=query,
            limit=limit,
            kinds=kinds,
            coupling_min=coupling_min,
            drive_id=drive_id or None,
            since_clock_ns=since_clock_ns,
        )

    @mcp.tool()  # type: ignore
    def get_drive_graph(
        drive_id: str = "", include_nodes: bool = True, max_nodes: int = 40
    ) -> dict:  # type: ignore
        return handle_get_drive_graph(
            drive_id=drive_id or None, include_nodes=include_nodes, max_nodes=max_nodes
        )

    @mcp.tool()  # type: ignore
    def subscribe_events(
        since: int = 0, types: str = "", limit: int = 20, poll_ms: int = 0
    ) -> dict:  # type: ignore
        return handle_subscribe_events(since=since, types=types, limit=limit, poll_ms=poll_ms)

    @mcp.tool()  # type: ignore
    def diagnose_freeze() -> dict:  # type: ignore
        return handle_diagnose_freeze()

    @mcp.tool()  # type: ignore
    def get_situation() -> dict:  # type: ignore
        return handle_get_situation()

    @mcp.tool()  # type: ignore
    def get_observation() -> dict:  # type: ignore
        return handle_get_observation()

    @mcp.tool()  # type: ignore
    def wrap_observation(dest_plane: str = "qoresence-research") -> dict:  # type: ignore
        return handle_wrap_observation(dest_plane=dest_plane)

    @mcp.tool()  # type: ignore
    def coach_clip(clip: str = "") -> dict:  # type: ignore
        return handle_coach_clip(clip=clip)

    @mcp.tool()  # type: ignore
    def narrate_clip(clip: str = "") -> dict:  # type: ignore
        return handle_narrate_clip(clip=clip)

    @mcp.tool()  # type: ignore
    def civif_live() -> dict:  # type: ignore
        return handle_civif_live()

    @mcp.tool()  # type: ignore
    def civif_highlights(limit: int = 8) -> dict:  # type: ignore
        return handle_civif_highlights(limit=limit)

    _mcp_fastmcp = mcp
    return mcp


def _read_token(tf: str | None = None) -> str | None:
    for p in [
        tf,
        os.getenv("MCP_TOKEN_FILE"),
        os.getenv("QORESENCE_AGENT_GLASS_TOKEN_FILE"),
        DEFAULT_TOKEN_FILE,
    ]:
        if not p:
            continue
        try:
            fp = Path(p)
            if fp.exists():
                t = fp.read_text(encoding="utf-8").strip()
                if t:
                    return t
        except Exception:
            continue
    tok = os.getenv("QORESENCE_AGENT_GLASS_TOKEN") or os.getenv("MCP_TOKEN")
    return tok.strip() if tok and tok.strip() else None


def _resolve_base() -> tuple[str, int]:
    h = os.getenv("QORESENCE_AGENT_GLASS_HOST") or os.getenv("QORESENCE_HOST") or DEFAULT_HOST
    ps = os.getenv("QORESENCE_AGENT_GLASS_PORT") or os.getenv("QORESENCE_PORT") or str(DEFAULT_PORT)
    try:
        port = int(ps)
    except Exception:
        port = DEFAULT_PORT
    if h == "0.0.0.0":
        h = DEFAULT_HOST
    return h, port


def _get_glass():
    try:
        from qoresence.agents.agent_glass import get_agent_glass

        return get_agent_glass()
    except Exception:
        return None


def _http_get(path: str, token: str | None = None) -> dict[str, Any]:
    h, port = _resolve_base()
    url = f"http://{h}:{port}{path}"
    if token is None:
        token = _read_token()
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            b = r.read()
            ct = r.headers.get("Content-Type", "")
            if "application/json" in ct or b[:1] in (b"{", b"["):
                return json.loads(b.decode("utf-8"))
            return {"ok": True, "raw": base64.b64encode(b).decode()}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            j = json.loads(body)
        except Exception:
            j = {"ok": False, "error": f"http_{e.code}", "body": body[:500]}
        j.setdefault("ok", False)
        j.setdefault("error", f"http_{e.code}")
        return j
    except Exception as e:
        return {
            "ok": False,
            "error": "http_unreachable",
            "hint": f"is Qoresence running with --agent-glass? ({e})",
        }


def _http_get_bytes(path: str, token: str | None = None):
    h, port = _resolve_base()
    url = f"http://{h}:{port}{path}"
    if token is None:
        token = _read_token()
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except Exception:
            return {"ok": False, "error": f"http_{e.code}", "body": body[:500]}
    except Exception as e:
        return {"ok": False, "error": "http_unreachable", "hint": str(e)}


def _http_post(path: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    h, port = _resolve_base()
    url = f"http://{h}:{port}{path}"
    if token is None:
        token = _read_token()
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            j = json.loads(body)
        except Exception:
            j = {"ok": False, "error": f"http_{e.code}", "body": body[:500]}
        j.setdefault("ok", False)
        return j
    except Exception as e:
        return {"ok": False, "error": "http_unreachable", "hint": str(e)}


def handle_get_snapshot() -> dict[str, Any]:
    g = _get_glass()
    if g is not None:
        try:
            return g.snapshot()
        except Exception as e:
            return {"ok": False, "error": "snapshot_failed", "hint": str(e)}
    r = _http_get("/api/agent/snapshot")
    if not r.get("ok") and r.get("error") == "http_unreachable":
        r["hint"] = (
            "is Qoresence running with --agent-glass? (--agent-glass enables 127.0.0.1:8765)"
        )
    return r


def handle_get_events(since: int = 0, types: str = "", limit: int = 20) -> dict[str, Any]:
    limit = max(1, min(500, int(limit)))
    since = max(0, int(since))
    csv = types.strip() if isinstance(types, str) else ""
    g = _get_glass()
    if g is not None:
        try:
            tl = [t.strip() for t in csv.split(",") if t.strip()] if csv else None
            return g.get_events(since=since, types=tl, limit=limit)
        except Exception as e:
            return {"ok": False, "error": "get_events_failed", "hint": str(e)}
    qs = f"?since={since}&limit={limit}"
    if csv:
        import urllib.parse as _up  # local import

        qs += "&types=" + _up.quote(csv)
    return _http_get(f"/api/agent/events{qs}")


def handle_get_health() -> dict[str, Any]:
    g = _get_glass()
    if g is not None:
        try:
            return g.health()
        except Exception as e:
            return {"ok": False, "error": "health_failed", "hint": str(e)}
    r = _http_get("/api/agent/health")
    if not r.get("ok") and r.get("error") == "http_unreachable":
        r["hint"] = (
            "is Qoresence running with --agent-glass? (--agent-glass enables 127.0.0.1:8765)"
        )
    return r


def handle_get_frame() -> dict[str, Any]:
    g = _get_glass()
    if g is not None:
        try:
            from qoresence.vision.clip_buffer import get_clip_buffer

            cb = get_clip_buffer()
            fn = getattr(cb, "latest_jpeg", None) or getattr(cb, "get_latest_jpeg", None)
            jpeg = fn() if callable(fn) else None
            if jpeg:
                return {
                    "ok": True,
                    "image": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode(),
                    "bytes": len(jpeg),
                    "clock_ns": time.monotonic_ns(),
                }
        except Exception:
            pass
    raw = _http_get_bytes("/api/agent/frame")
    if isinstance(raw, dict):
        return raw
    return {
        "ok": True,
        "image": "data:image/jpeg;base64," + base64.b64encode(raw).decode(),
        "bytes": len(raw),
        "clock_ns": time.monotonic_ns(),
    }



def handle_get_observation() -> dict[str, Any]:
    """Licensed witness pack — what the agent may say right now."""
    from qoresence.mcp.observation import build_observation

    snap = handle_get_snapshot()
    sit: dict[str, Any] = {}
    video: dict[str, Any] = {}
    coup: dict[str, Any] = {}
    clock_ns = None
    seq = None
    if isinstance(snap, dict) and snap.get("ok"):
        sit = snap.get("situation") or {}
        video = snap.get("video") or {}
        coup = snap.get("coupling") or {}
        clock_ns = snap.get("clock_ns")
        seq = snap.get("seq")
    elif isinstance(snap, dict) and snap.get("error") == "http_unreachable":
        return {
            "ok": False,
            "plane": "qoresence-observation",
            "error": "http_unreachable",
            "hint": snap.get("hint")
            or "is Qoresence running with --play --deck --agent-glass?",
            "must_not_invent": ["no_live_session"],
            "may_say": [],
        }
    glass = None
    try:
        from qoresence.deck.server import glass_link_info

        glass = glass_link_info()
    except Exception:
        glass = None
    pack = build_observation(
        situation=sit,
        video=video,
        coupling=coup,
        glass_link=glass,
        clock_ns=clock_ns,
        seq=seq,
    )
    if isinstance(snap, dict) and not snap.get("ok"):
        pack["snapshot_ok"] = False
        pack["must_not_invent"] = list(pack.get("must_not_invent") or []) + ["snapshot_degraded"]
    return pack


def handle_wrap_observation(dest_plane: str = "qoresence-research") -> dict[str, Any]:
    """Fail-closed research wrap. Never writes a truth-plane store."""
    from qoresence.vision.title_presence_ceremony import run_research_ceremony
    from qoresence.vision.title_presence_wrap import RESEARCH_DEST, dest_denied

    dest = str(dest_plane or RESEARCH_DEST).strip() or RESEARCH_DEST
    if dest_denied(dest):
        return {
            "ok": False,
            "reason": "dest_denied",
            "dest_plane": dest,
            "wrap": None,
            "ingredient": None,
        }
    rec = None
    try:
        ev = handle_get_events(since=0, types="title_presence", limit=8)
        if ev.get("ok"):
            for item in reversed(ev.get("events") or []):
                payload = item.get("payload") if isinstance(item, dict) else None
                if isinstance(payload, dict):
                    rec = payload
                    break
                if isinstance(item, dict) and item.get("plane"):
                    rec = item
                    break
    except Exception:
        rec = None
    if not isinstance(rec, dict):
        return {
            "ok": False,
            "reason": "no_record",
            "dest_plane": dest,
            "wrap": None,
            "ingredient": None,
            "hint": "no title_presence event on the bus",
        }
    return run_research_ceremony(rec, dest_plane=dest, persist=False)


def handle_get_situation() -> dict[str, Any]:
    snap = handle_get_snapshot()
    if not snap.get("ok"):
        return snap
    last = None
    try:
        ev = handle_get_events(since=0, types="visual_context", limit=1)
        if ev.get("ok") and ev.get("events"):
            last = ev["events"][-1]
    except Exception:
        pass
    return {
        "ok": True,
        "situation": snap.get("situation", {}),
        "coupling": snap.get("coupling", {}),
        "last_visual_context": last,
        "seq": snap.get("seq"),
        "clock_ns": snap.get("clock_ns"),
    }


def handle_search_clips(
    query: str = "",
    limit: int = 8,
    kinds: str = "",
    coupling_min: float = 0.0,
    drive_id: str | None = None,
    since_clock_ns: int = 0,
) -> dict[str, Any]:
    try:
        from qoresence.foundry.index import search_clips as _sc

        return _sc(
            query=query or "",
            limit=int(limit),
            kinds=str(kinds or ""),
            coupling_min=float(coupling_min) if coupling_min else 0.0,
            drive_id=drive_id or None,
            since_clock_ns=int(since_clock_ns) if since_clock_ns else 0,
        )
    except Exception as e:
        return {"ok": False, "error": "search_failed", "hint": str(e)}


def handle_coach_clip(clip: str = "") -> dict[str, Any]:
    try:
        from qoresence.foundry.coach import coach_clip as _cc

        return _cc(clip=str(clip or ""))
    except Exception as e:
        return {"ok": False, "error": "coach_failed", "hint": str(e)}


def handle_narrate_clip(clip: str = "") -> dict[str, Any]:
    try:
        from qoresence.foundry.narrative import narrate_clip as _nc

        return _nc(clip=str(clip or ""))
    except Exception as e:
        return {"ok": False, "error": "narrative_failed", "hint": str(e)}


def handle_civif_live() -> dict[str, Any]:
    try:
        from qoresence.foundry.cer_log import live_record
        from qoresence.foundry.coach import live_coach

        rec = live_record()
        coach = live_coach()
        return {"ok": True, "record": rec, "coach": coach, "plane": "qoresence-observation"}
    except Exception as e:
        return {"ok": False, "error": "civif_live_failed", "hint": str(e)}


def handle_civif_highlights(limit: int = 8) -> dict[str, Any]:
    try:
        from qoresence.foundry.highlights import rank_highlights

        return rank_highlights(limit=int(limit))
    except Exception as e:
        return {"ok": False, "error": "highlights_failed", "hint": str(e)}


def handle_get_drive_graph(
    drive_id: str | None = None, include_nodes: bool = True, max_nodes: int = 40
) -> dict[str, Any]:
    try:
        from qoresence.foundry.index import get_drive_graph as _gdg

        return _gdg(
            drive_id=drive_id or None, include_nodes=bool(include_nodes), max_nodes=int(max_nodes)
        )
    except Exception as e:
        return {"ok": False, "error": "drive_graph_failed", "hint": str(e)}


def handle_subscribe_events(
    since: int = 0, types: str = "", limit: int = 20, poll_ms: int = 1000
) -> dict[str, Any]:
    try:
        poll_ms = max(0, min(5000, int(poll_ms)))
        if poll_ms:
            import time as _t

            _t.sleep(min(0.5, poll_ms / 1000.0))
        ev = handle_get_events(since=int(since), types=str(types or ""), limit=int(limit))
        if not ev.get("ok"):
            return ev
        nxt = int(ev.get("next_seq") or int(since) or 0)
        return {
            "ok": True,
            "events": ev.get("events") or [],
            "count": ev.get("count") or 0,
            "next_since": nxt,
            "next_seq": nxt,
            "poll_again_ms": 1000,
            "hint": "call subscribe_events again with since=next_since for live tail",
        }
    except Exception as e:
        return {"ok": False, "error": "subscribe_failed", "hint": str(e)}


def handle_diagnose_freeze() -> dict[str, Any]:
    try:
        snap = handle_get_snapshot()
        health = handle_get_health()
        video: dict[str, Any] = {}
        coupling: dict[str, Any] = {}
        bus: dict[str, Any] = {}
        seq = 0
        if isinstance(snap, dict) and snap.get("ok"):
            video = snap.get("video") or {}
            coupling = snap.get("coupling") or {}
            bus = snap.get("bus") or {}
            seq = int(snap.get("seq") or 0)
        elif isinstance(health, dict):
            video = health.get("video") or {}
            coupling = health.get("coupling") or {}
            seq = int(health.get("seq") or 0)
        age_s = video.get("age_s")
        try:
            age_f = float(age_s) if age_s is not None else None
        except Exception:
            age_f = None
        frames = video.get("frames") or video.get("pushes") or 0
        has_frame = bool(video.get("has_frame"))
        frozen = False
        reasons: list[str] = []
        advice: list[str] = []
        if age_f is not None and age_f > 5.0:
            frozen = True
            reasons.append(f"video.age_s={age_f:.1f}s > 5s - frames stalled")
            advice.append(
                "not the capture card - capture thread likely deadlocked; run py-spy dump --pid <pid>, see AGENTS.md R1/R3/R4"
            )
        if not has_frame and (not frames or int(frames) == 0):
            reasons.append(
                "no frames yet (has_frame=false, frames=0) - is streamer running? (--play --deck --monitor)"
            )
        if seq == 0:
            reasons.append("glass seq=0 - RetinaEventBus not flowing")
        if not frozen and age_f is not None and age_f < 1.0 and has_frame:
            reasons.append(f"healthy: age_s={age_f:.2f}s, frames={frames}")
        diagnosis = "FROZEN" if frozen else ("NO_FRAMES" if not has_frame else "HEALTHY")
        return {
            "ok": True,
            "diagnosis": diagnosis,
            "frozen": frozen,
            "healthy": not frozen and has_frame,
            "video": video,
            "coupling": coupling,
            "bus": bus,
            "seq": seq,
            "age_s": age_f,
            "has_frame": has_frame,
            "reasons": reasons,
            "advice": advice or ["if degraded, lower --streamer-width/height or --streamer-fps 30"],
            "refs": ["AGENTS.md R1/R3/R4", "docs/AGENT_GLASS.md#threading-invariant"],
        }
    except Exception as e:
        return {"ok": False, "error": "diagnose_failed", "hint": str(e)}


TOOL_DEFS = [
    {
        "name": "get_snapshot",
        "description": "Curated PS5 HDMI + input + game-state + coupling + video health. No capture.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_events",
        "description": "Cursor-paginated RetinaEventBus. since is _agent_seq, types csv, limit 1..500.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "since": {"type": "integer", "minimum": 0, "default": 0},
                "types": {"type": "string", "default": ""},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 20},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_health",
        "description": "Fast liveness: running, seq, video {age_s,frames}, coupling.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_frame",
        "description": "Latest JPEG as base64 data uri. Throttled 10fps/client.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "search_clips",
        "description": "Foundry RAG: keyword search over clips chapters+buttons+graph+timeline. query free text, limit 1..20, kinds csv, coupling_min 0..1, drive_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
                "kinds": {"type": "string", "default": ""},
                "coupling_min": {"type": "number", "minimum": 0, "maximum": 1, "default": 0},
                "drive_id": {"type": "string", "default": ""},
                "since_clock_ns": {"type": "integer", "minimum": 0, "default": 0},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "coach_clip",
        "description": (
            "CIVIF observation coach for a clip sidecar. Timing/pattern withheld unless "
            "input.bodied. Score digits withheld unless board_locked. Read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "clip": {"type": "string", "description": "Clip stem or *.coupling.json path"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "narrate_clip",
        "description": (
            "Fail-closed narrative for a civif-v0 sidecar. Same withhold rules as coach_clip. Read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "clip": {"type": "string", "description": "Clip stem or *.coupling.json path"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "civif_live",
        "description": "Live Coupled Event Record + fail-closed coach. Timing/pattern withheld unless DualSense is bodied on this host.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "civif_highlights",
        "description": "Rank clips by civif-v0 coupling / locked score / bodied input. Read-only. No invented digits.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_drive_graph",
        "description": "DriveGraph for active or drive_id: phase/climax/nodes/ranking + why_line. Software-only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "drive_id": {"type": "string", "default": ""},
                "include_nodes": {"type": "boolean", "default": True},
                "max_nodes": {"type": "integer", "minimum": 1, "maximum": 200, "default": 40},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "subscribe_events",
        "description": "Proactive glass: poll RetinaEventBus since=_agent_seq, types csv, limit 1..500. Returns next_since for live tail.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "since": {"type": "integer", "minimum": 0, "default": 0},
                "types": {"type": "string", "default": ""},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 20},
                "poll_ms": {"type": "integer", "minimum": 0, "maximum": 5000, "default": 0},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "diagnose_freeze",
        "description": "Software-only freeze triage: checks video.age_s/frames, glass seq, bus; returns diagnosis FROZEN/HEALTHY/NO_FRAMES.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_situation",
        "description": "Merged situation+coupling+last visual_context.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_observation",
        "description": (
            "Fail-closed witness pack: plane-tagged title/score/phrase/glass the agent MAY say. "
            "Unlocked scores and localhost glass URLs are silenced. Call this before speaking."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "wrap_observation",
        "description": (
            "Fail-closed re-wrap of the last title_presence record onto qoresence-research. "
            "Requires QORESENCE_WRAP_GRANT_ID. Refuses qortroller-truth. Does not mutate the optical record."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dest_plane": {"type": "string", "default": "qoresence-research"},
            },
            "additionalProperties": False,
        },
    },
]
RESOURCE_DEFS = [
    {
        "uri": "qoresence://snapshot",
        "name": "snapshot",
        "mimeType": "application/json",
        "description": "Live snapshot",
    },
    {
        "uri": "qoresence://events",
        "name": "events",
        "mimeType": "application/json",
        "description": "Event log",
    },
]
PROMPT_DEFS = [
    {"name": "coach_clutch", "description": "Clutch coach prompt", "arguments": []},
    {"name": "debug_freeze", "description": "Freeze checklist", "arguments": []},
    {"name": "speak_licensed", "description": "Speak only from get_observation", "arguments": []},
]
HANDLERS = {
    "get_snapshot": lambda a: handle_get_snapshot(),
    "get_events": lambda a: handle_get_events(
        since=int(a.get("since", 0)), types=str(a.get("types", "")), limit=int(a.get("limit", 20))
    ),
    "get_health": lambda a: handle_get_health(),
    "get_frame": lambda a: handle_get_frame(),
    "search_clips": lambda a: handle_search_clips(
        query=str(a.get("query", "")),
        limit=int(a.get("limit", 8)),
        kinds=str(a.get("kinds", "")),
        coupling_min=float(a.get("coupling_min", 0) or 0),
        drive_id=(str(a.get("drive_id", "")).strip() or None),
        since_clock_ns=int(a.get("since_clock_ns", 0) or 0),
    ),
    "coach_clip": lambda a: handle_coach_clip(clip=str(a.get("clip", "") or "")),
    "narrate_clip": lambda a: handle_narrate_clip(clip=str(a.get("clip", "") or "")),
    "civif_live": lambda a: handle_civif_live(),
    "civif_highlights": lambda a: handle_civif_highlights(limit=int(a.get("limit", 8) or 8)),
    "get_drive_graph": lambda a: handle_get_drive_graph(
        drive_id=(str(a.get("drive_id", "")).strip() or None),
        include_nodes=bool(a.get("include_nodes", True)),
        max_nodes=int(a.get("max_nodes", 40)),
    ),
    "subscribe_events": lambda a: handle_subscribe_events(
        since=int(a.get("since", 0)),
        types=str(a.get("types", "")),
        limit=int(a.get("limit", 20)),
        poll_ms=int(a.get("poll_ms", 0)),
    ),
    "diagnose_freeze": lambda a: handle_diagnose_freeze(),
    "get_situation": lambda a: handle_get_situation(),
    "get_observation": lambda a: handle_get_observation(),
    "wrap_observation": lambda a: handle_wrap_observation(
        dest_plane=str(a.get("dest_plane") or "qoresence-research")
    ),
}


def _rpc_result(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _handle_request(msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}
    is_notif = "id" not in msg
    if method == "initialize":
        return _rpc_result(
            req_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "tools/list":
        return _rpc_result(req_id, {"tools": TOOL_DEFS})
    if method == "resources/list":
        return _rpc_result(req_id, {"resources": RESOURCE_DEFS})
    if method == "prompts/list":
        return _rpc_result(req_id, {"prompts": PROMPT_DEFS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        h = HANDLERS.get(name)
        if not h:
            return _rpc_error(req_id, -32601, f"unknown tool: {name}")
        try:
            result = h(args)
            text = json.dumps(result, indent=2, default=str)
            return _rpc_result(req_id, {"content": [{"type": "text", "text": text}]})
        except Exception as e:
            log.exception("tools/call %s failed", name)
            return _rpc_error(req_id, -32603, f"tool {name} failed: {e}")
    if method == "resources/read":
        uri = params.get("uri", "")
        if uri == "qoresence://snapshot":
            snap = handle_get_snapshot()
            return _rpc_result(
                req_id,
                {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(snap, indent=2, default=str),
                        }
                    ]
                },
            )
        if uri.startswith("qoresence://events"):
            import urllib.parse as _up

            parsed = _up.urlparse(uri)
            qs = _up.parse_qs(parsed.query)
            since = int(qs.get("since", ["0"])[0])
            types = qs.get("types", [""])[0]
            limit = int(qs.get("limit", ["20"])[0])
            ev = handle_get_events(since=since, types=types, limit=limit)
            return _rpc_result(
                req_id,
                {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(ev, indent=2, default=str),
                        }
                    ]
                },
            )
        return _rpc_error(req_id, -32602, f"unknown resource: {uri}")
    if method == "prompts/get":
        name = params.get("name")
        if name == "speak_licensed":
            return _rpc_result(
                req_id,
                {
                    "description": "Speak only licensed observation",
                    "messages": [
                        {
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": (
                                    "Call get_observation first. Speak only items in may_say. "
                                    "If score.claim is false do not invent digits. "
                                    "If glass.lan is false do not tell anyone to open the URL on a phone. "
                                    "Cite plane qoresence-observation. Never claim humanity or eligibility."
                                ),
                            },
                        }
                    ],
                },
            )
        if name == "coach_clutch":
            return _rpc_result(
                req_id,
                {
                    "description": "Clutch coach",
                    "messages": [
                        {
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": "You are Qoresence clutch coach. Call get_observation, then search_clips, then coach_clip / narrate_clip on a hit. Timing/pattern notes are withheld unless input.bodied (DualSense often stays on the PS5). Do not invent score digits unless board_locked. Cite clock_ns. Do not write clips via MCP — operator uses POST /api/agent/clip.",
                            },
                        }
                    ],
                },
            )
        if name == "debug_freeze":
            return _rpc_result(
                req_id,
                {
                    "description": "Freeze checklist",
                    "messages": [
                        {
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": "If video.age_s>5s and frames stalled, run py-spy — not capture card. Check AGENTS.md R1/R3/R4.",
                            },
                        }
                    ],
                },
            )
        return _rpc_error(req_id, -32602, f"unknown prompt: {name}")
    if method == "ping":
        return _rpc_result(req_id, {})
    if is_notif:
        return None
    return _rpc_error(req_id, -32601, f"Method not found: {method}")


def _serve_stdio() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if isinstance(msg, list):
            rs = []
            for m in msg:
                r = _handle_request(m)
                if r is not None:
                    rs.append(r)
            if rs:
                sys.stdout.write(json.dumps(rs) + "\n")
                sys.stdout.flush()
        else:
            resp = _handle_request(msg)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Qoresence MCP server (Glass D)")
    p.add_argument("--help-tools", action="store_true", help="list tools and exit")
    args = p.parse_args()
    if args.help_tools:
        print(json.dumps(TOOL_DEFS, indent=2))  # noqa: T201
        return
    if os.getenv("QORESENCE_MCP_USE_FASTMCP") == "1":
        fastmcp = _get_fastmcp()
        if fastmcp is not None:
            fastmcp.run()
            return
        log.warning(
            "QORESENCE_MCP_USE_FASTMCP=1 but mcp package not installed; falling back to stdio"
        )
    _serve_stdio()


if __name__ == "__main__":
    main()
