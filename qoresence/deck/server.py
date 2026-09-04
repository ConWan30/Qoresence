"""Retina Deck — ws://localhost:8765/retina + HTTP overlay/deck.

One brain (RetinaEventBus / SituationModel) -> three glasses:
  A) Clutch Lens  http://localhost:8765/overlay.html  (OBS Browser Source, transparent)
  A2) Pattern B HDMI pixels  http://localhost:8765/obs-live.html  (OBS Browser Source; not raw /video)
  B) Retina Rail  http://localhost:8765/deck.html      (local drawer + hotkey)
  C) Ghost Replay via same ws feed

No cloud. Local only. FastAPI if installed, stdlib fallback otherwise.
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

DECK_HOST = "127.0.0.1"
DECK_PORT = 8765
WS_PATH = "/retina"

# Wire contract — bump only on breaking field changes.
SCHEMA_VERSION = "qoresence-deck-v0"
# Ghost Theater LIVE default: full PS5 HDMI rate when Qoresence owns the card
DEFAULT_LIVE_FPS = 60.0
LIVE_FPS_MIN = 5.0
LIVE_FPS_MAX = 60.0

# FastAPI must be importable at module scope when using
# `from __future__ import annotations`. Nested endpoints get stringized
# annotations resolved via module globals — a local `from fastapi import
# WebSocket` leaves websocket_param_name=None, so FastAPI treats the param
# as a required query field and uvicorn rejects the upgrade with HTTP 403.
# That is exactly OBS Browser Source FIN_WAIT_2 thrash + clients:0.
try:
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore[misc, assignment]
    Request = None  # type: ignore[misc, assignment]
    WebSocket = None  # type: ignore[misc, assignment]
    WebSocketDisconnect = None  # type: ignore[misc, assignment]
    FileResponse = None  # type: ignore[misc, assignment]
    HTMLResponse = None  # type: ignore[misc, assignment]
    JSONResponse = None  # type: ignore[misc, assignment]
    Response = None  # type: ignore[misc, assignment]
    _HAS_FASTAPI = False

# ---------------------------------------------------------------------------
# State store — updated by RetinaEventBus subscriber (cli wires this)
# ---------------------------------------------------------------------------


# Coalesce /health + /api/situation + WS snapshot so LIVE JPEG is not queued
# behind three full companion/drive-graph builds on the same threadpool.
_SNAP_MEMO_TTL_S = 0.04
_snap_memo_lock = threading.Lock()
_snap_memo_at = 0.0
_snap_memo: dict[str, Any] | None = None


def _snapshot_memo_get() -> dict[str, Any] | None:
    now = time.monotonic()
    with _snap_memo_lock:
        if _snap_memo is not None and now - _snap_memo_at < _SNAP_MEMO_TTL_S:
            return _snap_memo
    return None


def _snapshot_memo_put(out: dict[str, Any]) -> None:
    global _snap_memo_at, _snap_memo
    with _snap_memo_lock:
        _snap_memo = out
        _snap_memo_at = time.monotonic()


@dataclass
class DeckState:
    situation: dict[str, Any] = field(default_factory=dict)
    last_moment: dict[str, Any] | None = None
    moments: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 1.12
    fps: int = 6
    updated_ns: int = 0  # monotonic ns of last live update — for staleness check
    jsonl_path: str = "logs/events.jsonl"

    def snapshot(self) -> dict[str, Any]:
        memo = _snapshot_memo_get()
        if memo is not None:
            return memo
        out = self._snapshot_fresh()
        _snapshot_memo_put(out)
        return out

    def _snapshot_fresh(self) -> dict[str, Any]:
        video: dict[str, Any] = {
            "has_frame": False,
            "age_s": None,
            "frames": 0,
            "live_fps_default": DEFAULT_LIVE_FPS,
        }
        try:
            from qoresence.vision.clip_buffer import get_clip_buffer

            video = get_clip_buffer().stats()
            video["live_fps_default"] = DEFAULT_LIVE_FPS
        except Exception:
            pass
        try:
            from qoresence.monitor.frame_hub import get_frame_hub

            hub = get_frame_hub().stats()
            video["hub_age_s"] = hub.get("age_s")
            video["hub_seq"] = hub.get("seq")
            video["hub_has_frame"] = bool(hub.get("has_frame"))
            if hub.get("has_frame"):
                ch = str(hub.get("crop_hash") or "")
                if ch:
                    video["crop_hash"] = ch
            if hub.get("has_frame") and hub.get("age_s") is not None:
                if video.get("age_s") is None or float(hub["age_s"]) < float(video["age_s"] or 9e9):
                    video["age_s"] = hub["age_s"]
                    video["has_frame"] = True
        except Exception:
            pass
        controller: dict[str, Any] = {}
        try:
            from qoresence.lobes.controller import get_controller_runtime

            rt = get_controller_runtime()
            if rt is not None:
                stats = rt.get_stats()
                controller.update(
                    {
                        "connected": bool(stats.get("connected")),
                        "waiting": bool(stats.get("waiting")),
                        "device": stats.get("device"),
                        "transport": stats.get("transport"),
                        "reports": stats.get("reports", 0),
                        "reconnects": stats.get("reconnects", 0),
                    }
                )
        except Exception:
            pass
        try:
            from qoresence.sync.input_ring import get_input_ring
            from qoresence.sync.ivc import get_ivc, get_last_coupling

            if get_ivc() is not None:
                coup = get_last_coupling()
                controller.update(
                    {
                        "buttons": get_input_ring().latest_buttons()[:8],
                        "coupling": coup.get("coupling", 0.0),
                        "coupling_ema": coup.get("coupling_ema", coup.get("coupling", 0.0)),
                        "hold_energy": coup.get("hold_energy", 0.0),
                        "edge_energy": coup.get("edge_energy", 0.0),
                        "phrase": None,
                        "phrase_conf": 0.0,
                        "coupling_ticket_id": coup.get("coupling_ticket_id") or "",
                        "frame_seq": coup.get("frame_seq", 0),
                        "input_energy": coup.get("input_energy", 0.0),
                        "input_events": coup.get("input_events", 0),
                        "lead_ms": coup.get("lead_ms"),
                        "imu_bodied": bool(coup.get("imu_bodied")),
                        "imu_precursor_ms": coup.get("imu_precursor_ms"),
                        "imu_precursor_name": coup.get("imu_precursor_name"),
                        "binds": int(coup.get("binds") or 0),
                        "last_bind_ms": coup.get("last_bind_ms"),
                        "last_bind_kind": coup.get("last_bind_kind"),
                        "last_bind_hid": coup.get("last_bind_hid"),
                        "lag_band_ms": coup.get("lag_band_ms"),
                        "stick_gyro_r": coup.get("stick_gyro_r"),
                        "stick_motion_r": coup.get("stick_motion_r"),
                        "path": coup.get("path") or "fast",
                        "lag_center_ms": coup.get("lag_center_ms"),
                        "lag_jitter_ms": coup.get("lag_jitter_ms"),
                        "pll_lock": bool(coup.get("pll_lock")),
                        "bind_offset_ms": coup.get("bind_offset_ms"),
                        "bind_conf": coup.get("bind_conf"),
                    }
                )
        except Exception:
            pass
        out: dict[str, Any] = {
            "type": "snapshot",
            "schema_version": SCHEMA_VERSION,
            "situation": self.situation,
            "last_moment": self.last_moment,
            "moments": self.moments[-3:],
            "latency_ms": self.latency_ms,
            "fps": self.fps,
            "updated_ns": self.updated_ns,
            "video": video,
        }
        try:
            from qoresence.deck.live_paint import snapshot_live_paint

            lp = snapshot_live_paint(self.situation)
            video["paint"] = lp.paint
            video["live_seq"] = lp.live_seq
            video["widget_seq"] = lp.widget_seq
            video["same_seq"] = lp.same_seq
            video["plane_dim"] = lp.plane_dim
            video["paint_reason"] = lp.reason
            # Last-good BGR is not an accepted LIVE frame. Keep hub occupancy
            # when Dark Theater only ghosts widgets (menu / overlay-rejected).
            if not lp.paint and lp.reason in {"no_frame", "blank"}:
                video["has_frame"] = False
            try:
                from qoresence.sync.ghost_stick import snapshot_ghost_stick

                out["ghost_stick"] = snapshot_ghost_stick(
                    live_paint=lp, situation=self.situation
                )
            except Exception:
                out["ghost_stick"] = {"enabled": False, "paint": False, "reason": "off"}
        except Exception:
            pass
        try:
            from qoresence.vision.confirm_ticket import get_ticket_book

            out["confirm"] = get_ticket_book().mismatch()
        except Exception:
            out["confirm"] = {"last_fast": None, "last_confirm": None, "lag_ns": None}
        try:
            from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

            out["scoreboard_vlm"] = get_scoreboard_vlm().stats()
        except Exception:
            out["scoreboard_vlm"] = {"enabled": False}
        try:
            from qoresence.operator_bus.mailbox import get_operator_mailbox

            out["operator_bus"] = get_operator_mailbox().stats()
        except Exception:
            out["operator_bus"] = {"inbox": 0, "outbox": 0}
        if controller:
            out["controller"] = controller
        # Session timeline why-strip / active drive (optional)
        try:
            from qoresence.agents.session_timeline import get_session_timeline

            snap = get_session_timeline().snapshot(recent_n=12)
            out["timeline"] = {
                "why_last": snap.get("why_last"),
                "active_drive": snap.get("active_drive"),
                "count": snap.get("count", 0),
                "drive_graph": snap.get("drive_graph"),
            }
        except Exception:
            pass
        try:
            from qoresence.agents.companion import build_companion
            from qoresence.agents.society import get_society
            from qoresence.sync.ivc import get_last_coupling

            soc = get_society()
            tl = out.get("timeline") if isinstance(out.get("timeline"), dict) else {}
            out["companion"] = build_companion(
                situation=self.situation if isinstance(self.situation, dict) else {},
                coupling=get_last_coupling(),
                moments=list(self.moments[-8:]),
                last_moment=self.last_moment if isinstance(self.last_moment, dict) else None,
                society=soc.stats() if soc is not None else {"enabled": False},
                drive_graph=(tl or {}).get("drive_graph"),
                why_last=(tl or {}).get("why_last"),
            )
        except Exception:
            pass
        try:
            from qoresence.agents.actuators import actuators_health

            out["actuators"] = actuators_health(out)
        except Exception:
            out["actuators"] = {"registry": [], "receipts": []}
        # LAYER A: observation object on the Deck wire (sheet-from-picture, named clutch, conflict)
        try:
            from qoresence.deck.observation_wire import build_observation_wire

            out["observation"] = build_observation_wire(self.situation)
        except Exception:
            out["observation"] = None
        return out


def _situation_payload() -> dict[str, Any]:
    """Deck snapshot plus top-level coupling for Mobile / Native Glass.

    Native Glass polls ``/api/situation`` for clutch haptics. Coupling used to
    live only on ``/health`` and under ``controller`` — the app never saw a
    climax and never fired. Keep digits fail-closed: this helper does not
    invent scores.
    """
    out = _state.snapshot()
    try:
        from qoresence.sync.ivc import get_last_coupling

        coup: dict[str, Any] = dict(get_last_coupling())
    except Exception:
        coup = {"imu_bodied": False, "coupling": 0.0, "binds": 0, "phrase": None}
    out.get("controller") if isinstance(out.get("controller"), dict) else {}
    # play-phrase DELETED — never emit IDLE/HUDDLE/SPRINT into situation
    coup["phrase"] = None
    coup["phrase_conf"] = 0.0
    if "phrase_live" in coup:
        coup["phrase_live"] = False
    climax = 0.0
    try:
        tl = out.get("timeline") if isinstance(out.get("timeline"), dict) else {}
        why = (tl or {}).get("why_last") if isinstance((tl or {}).get("why_last"), dict) else {}
        if why and why.get("climax_score") is not None:
            climax = float(why.get("climax_score") or 0.0)
        graph = (
            (tl or {}).get("drive_graph") if isinstance((tl or {}).get("drive_graph"), dict) else {}
        )
        cl = (graph or {}).get("climax") if isinstance((graph or {}).get("climax"), dict) else {}
        if cl and cl.get("score") is not None:
            climax = max(climax, float(cl.get("score") or 0.0))
    except (TypeError, ValueError):
        climax = 0.0
    coup["climax_score"] = climax
    out["coupling"] = coup
    out["schema_version"] = SCHEMA_VERSION
    try:
        from qoresence.agents.match_agent import surface_last_note

        out["match_agent"] = surface_last_note()
    except Exception:
        out["match_agent"] = {}
    return out


_state = DeckState()
_deck_config: Any = None
_deck_bind_host: str = DECK_HOST
_deck_bind_port: int = DECK_PORT
_ws_clients: set[Any] = set()
_ws_queues: dict[Any, asyncio.Queue[str]] = {}
_ws_client_count = 0
_loop: asyncio.AbstractEventLoop | None = None
_broadcast_lock = threading.Lock()
_broadcast_pending: deque[dict[str, Any]] = deque(maxlen=64)
_broadcast_scheduled = False
_BROADCAST_QUEUE_SIZE = 32


def update_situation(situation: dict[str, Any], latency_ms: float | None = None) -> None:
    # Reject stale/empty payloads — live feed must have at least one real field
    if not situation or not any(
        situation.get(k) is not None
        for k in (
            "home_score",
            "away_score",
            "quarter",
            "down",
            "kills",
            "health",
            "game_state",
            "score_home",
        )
    ):
        return
    import time as _t

    sit = dict(situation)
    if sit.get("frame_seq") is None:
        try:
            from qoresence.monitor.frame_hub import get_frame_hub

            sit["frame_seq"] = int(get_frame_hub().get_latest_stamp().get("seq") or 0)
        except Exception:
            sit["frame_seq"] = 0
    _state.situation = sit
    _state.updated_ns = _t.monotonic_ns()
    if latency_ms is not None:
        _state.latency_ms = latency_ms
    video: dict[str, Any] = {}
    try:
        from qoresence.deck.live_paint import snapshot_live_paint

        lp = snapshot_live_paint(sit)
        video = {
            "paint": lp.paint,
            "live_seq": lp.live_seq,
            "widget_seq": lp.widget_seq,
            "same_seq": lp.same_seq,
            "plane_dim": lp.plane_dim,
            "paint_reason": lp.reason,
            "has_frame": bool(lp.has_frame),
        }
        try:
            from qoresence.monitor.frame_hub import get_frame_hub

            ch = str(get_frame_hub().stats().get("crop_hash") or "")
            if ch:
                video["crop_hash"] = ch
        except Exception:
            pass
    except Exception:
        pass
    msg: dict[str, Any] = {
        "type": "situation",
        "schema_version": SCHEMA_VERSION,
        "payload": sit,
        "latency_ms": _state.latency_ms,
        "updated_ns": _state.updated_ns,
    }
    if video:
        msg["video"] = video
    _broadcast(msg)


def _norm_title(title: Any) -> str:
    import re

    t = str(title or "").lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s\-']", "", t)
    return t[:100]


def push_moment(moment: dict[str, Any]) -> None:
    # Only allow live-triggered moments (must have title)
    if not moment or not moment.get("title"):
        return
    import time as _t

    moment = dict(moment)
    now_ns = _t.monotonic_ns()
    title_n = _norm_title(moment.get("title"))
    action = str(moment.get("action") or "chat")
    # Chat spam guard: same normalized title within 90s (any path/source)
    # Clips keep a short 2s window only.
    try:
        window_ns = 90_000_000_000 if action != "clip" else 2_000_000_000
        if title_n:
            for prev in reversed(_state.moments[-12:]):
                if _norm_title(prev.get("title")) != title_n:
                    continue
                if action == "clip" and str(prev.get("action") or "") != "clip":
                    continue
                last_ts = int(prev.get("ts_ns") or 0)
                if last_ts and (now_ns - last_ts) < window_ns:
                    return
        last = _state.last_moment
        if last and _norm_title(last.get("title")) == title_n:
            last_ts = int(last.get("ts_ns") or 0)
            if last_ts and (now_ns - last_ts) < window_ns:
                return
    except Exception:
        pass
    moment.setdefault("ts_ns", now_ns)
    _state.last_moment = moment
    _state.moments.append(moment)
    if len(_state.moments) > 100:
        _state.moments = _state.moments[-100:]
    _broadcast({"type": "moment", "payload": moment})


def push_stem_program(payload: dict[str, Any]) -> None:
    """Fan stem_program to /retina. Never takes a lobe lock."""
    if not isinstance(payload, dict):
        return
    _broadcast({"type": "stem_program", "payload": dict(payload)})


# ---------------------------------------------------------------------------
# AgentGlass helpers (read-only snapshot for external agents — no capture)
# ---------------------------------------------------------------------------

_agent_frame_last: dict[str, float] = {}
_agent_clip_last: float = 0.0
_agent_eps: dict[str, list[float]] = {}
_agent_lock = threading.Lock()


def _local_client_required_response(request: Any) -> Any | None:
    """Fail closed for state-changing routes when the client is not loopback."""
    from qoresence.security.redact import client_is_loopback

    if client_is_loopback(request):
        return None
    return JSONResponse({"ok": False, "error": "local_client_required"}, status_code=403)


def _agent_check_token(request: Any) -> bool:
    try:
        from qoresence.agents.agent_glass import get_agent_glass

        g = get_agent_glass()
        cfg = getattr(g, "config", None) if g else None
        require = bool(getattr(cfg, "require_token", False)) if cfg else False
        if not require:
            return True
        token_file = (
            getattr(cfg, "token_file", ".secrets/agent_glass.token")
            if cfg
            else ".secrets/agent_glass.token"
        )
        auth = ""
        try:
            auth = request.headers.get("authorization", "") if hasattr(request, "headers") else ""
        except Exception:
            auth = ""
        if not auth.lower().startswith("bearer "):
            return False
        token = auth[7:].strip()
        try:
            exp = pathlib.Path(token_file).read_text(encoding="utf-8").strip().split()[0]
            return token == exp and len(token) >= 16
        except Exception:
            return False
    except Exception:
        return True


def _agent_eps_ok(client_id: str, max_eps: float = 20.0) -> bool:
    now = time.monotonic()
    window = 1.0
    with _agent_lock:
        lst = _agent_eps.get(client_id)
        if lst is None:
            lst = []
            _agent_eps[client_id] = lst
        # prune
        cutoff = now - window
        while lst and lst[0] < cutoff:
            lst.pop(0)
        if len(lst) >= max_eps:
            return False
        lst.append(now)
        return True


def _agent_snapshot_payload() -> dict[str, Any]:
    try:
        from qoresence.agents.agent_glass import get_agent_glass

        g = get_agent_glass()
        if g is not None:
            snap = dict(g.snapshot())
            snap.setdefault("schema_version", SCHEMA_VERSION)
            return snap
    except Exception:
        pass
    # fallback: minimal snapshot from DeckState + clip buffer
    video: dict[str, Any] = {"has_frame": False}
    try:
        from qoresence.vision.clip_buffer import get_clip_buffer

        video = get_clip_buffer().stats()
    except Exception:
        pass
    coupling: dict[str, Any] = {}
    try:
        from qoresence.sync.ivc import get_last_coupling

        coupling = get_last_coupling()
    except Exception:
        coupling = {"coupling": 0.0}
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "enabled": True,
        "state": _state.snapshot(),
        "video": video,
        "coupling": coupling,
        "clock_ns": time.monotonic_ns(),
    }


def _enqueue_ws_message(queue: asyncio.Queue[str], data: str) -> None:
    try:
        queue.put_nowait(data)
        return
    except asyncio.QueueFull:
        pass
    try:
        queue.get_nowait()
    except asyncio.QueueEmpty:
        return
    try:
        queue.put_nowait(data)
    except asyncio.QueueFull:
        pass


def _drain_broadcast() -> None:
    global _broadcast_scheduled
    with _broadcast_lock:
        batch = list(_broadcast_pending)
        _broadcast_pending.clear()
        _broadcast_scheduled = False

    if batch:
        queues = list(_ws_queues.values())
        for msg in batch:
            data = json.dumps(msg, separators=(",", ":"))
            for queue in queues:
                _enqueue_ws_message(queue, data)

    with _broadcast_lock:
        if _broadcast_pending and not _broadcast_scheduled:
            _broadcast_scheduled = True
            reschedule = True
        else:
            reschedule = False
    if reschedule:
        loop = _loop
        if loop is not None:
            loop.call_soon(_drain_broadcast)


async def _send_deck_queue(websocket: Any, queue: asyncio.Queue[str]) -> None:
    while True:
        data = await queue.get()
        try:
            await websocket.send_text(data)
        except Exception:
            try:
                await websocket.close()
            except Exception:
                pass
            return


def _broadcast(msg: dict[str, Any]) -> None:
    global _broadcast_scheduled
    loop = _loop
    if loop is None:
        return
    with _broadcast_lock:
        if msg.get("type") == "situation":
            for index in range(len(_broadcast_pending) - 1, -1, -1):
                if _broadcast_pending[index].get("type") == "situation":
                    del _broadcast_pending[index]
                    break
        _broadcast_pending.append(dict(msg))
        if _broadcast_scheduled:
            return
        _broadcast_scheduled = True
    try:
        loop.call_soon_threadsafe(_drain_broadcast)
    except RuntimeError:
        with _broadcast_lock:
            _broadcast_scheduled = False


def _fanout_stats() -> dict[str, int]:
    with _broadcast_lock:
        pending = len(_broadcast_pending)
        clients = _ws_client_count
    return {"clients": clients, "pending": pending, "capacity": _broadcast_pending.maxlen or 0}


# ---------------------------------------------------------------------------
# FastAPI app (preferred)
# ---------------------------------------------------------------------------


_GLASS_HTML_NAMES = frozenset(
    {"deck.html", "overlay.html", "studio.html", "mobile.html", "index.html"}
)


def _glass_candidates() -> list[pathlib.Path]:
    here = pathlib.Path(__file__).resolve()
    repo = here.parents[2]
    # Packaged SPA first. A stale gitignored glass/dist (older Vite ship)
    # hid HDMI on livePaint flicker while /live.jpg was 200.
    return [here.with_name("glass_spa"), repo / "glass" / "dist"]


def _glass_dist() -> pathlib.Path:
    for p in _glass_candidates():
        if (p / "index.html").is_file():
            return p
    return _glass_candidates()[0]


def _glass_index_path() -> pathlib.Path | None:
    for p in _glass_candidates():
        idx = p / "index.html"
        if idx.is_file():
            return idx
    return None


_CLIP_DOCK_JS = "clip-dock.js"
_CLIP_DOCK_CSS = "clip-dock.css"


def _clip_dock_snippet() -> str:
    return (
        f'<link rel="stylesheet" href="/{_CLIP_DOCK_CSS}?v=standdown3">'
        f'<script src="/{_CLIP_DOCK_JS}?v=standdown3" defer></script>'
    )


def _with_clip_dock(html: str) -> str:
    """Pin HDMI clip tiles on every Theater page, even if the SPA is stale."""
    if _CLIP_DOCK_JS in html:
        return html
    inject = _clip_dock_snippet()
    if "</body>" in html:
        return html.replace("</body>", inject + "</body>", 1)
    return html + inject


def _html(name: str) -> str:
    """Prefer built Retina Deck glass SPA; fall back to qoresence/deck/*.html."""
    body = ""
    if name in _GLASS_HTML_NAMES:
        gi = _glass_index_path()
        if gi is not None:
            body = gi.read_text(encoding="utf-8")
    if not body:
        p = pathlib.Path(__file__).with_name(name)
        if p.exists():
            body = p.read_text(encoding="utf-8")
        else:
            body = f"<h1>{name} missing</h1>"
    if name in _GLASS_HTML_NAMES or name == "civif.html":
        return _with_clip_dock(body)
    return body


def _glass_js_name() -> str:
    import re

    m = re.search(r"/assets/(index-[A-Za-z0-9_-]+\.js)", _html("deck.html"))
    return m.group(1) if m else "none"


def _guess_lan_ip() -> str | None:
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        return str(ip) if ip and not str(ip).startswith("127.") else None
    except Exception:
        return None
    finally:
        sock.close()


def glass_link_info(host: str | None = None, port: int | None = None) -> dict[str, Any]:
    """Honest Mobile Glass URL. Never invents a public CDN."""
    bind = str(host if host is not None else _deck_bind_host or DECK_HOST)
    p = int(port if port is not None else _deck_bind_port or DECK_PORT)
    loopback = bind in {"127.0.0.1", "localhost", "::1"}
    wildcard = bind in {"0.0.0.0", "::", "[::]"}
    display = bind
    if wildcard:
        display = _guess_lan_ip() or bind
    lan = (not loopback) or wildcard
    if loopback:
        note = "Localhost only. Enable LAN bind (--deck-host 0.0.0.0 or --deck-bind) to open on a phone."
    elif wildcard and display in {"0.0.0.0", "::"}:
        note = (
            "LAN bind is on but this PC's LAN IP could not be guessed. Use the PC address on Wi-Fi."
        )
    else:
        note = "LAN opt-in. Same Wi-Fi only. Not a public stream."
    return {
        "bind": bind,
        "port": p,
        "lan": bool(lan and not loopback),
        "url": f"http://{display}:{p}/mobile.html",
        "note": note,
        "path": "/mobile.html",
    }


_PLACEHOLDER_JPEG: bytes | None = None
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_GLASS_APK_CANDIDATES = (
    _REPO_ROOT / "qoresence-glass-debug.apk",
    _REPO_ROOT / "native" / "android" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk",
)


def _glass_apk_path() -> pathlib.Path | None:
    """Newest debug APK for same-Wi-Fi sideload. View-only; never a capture owner."""
    found = [p for p in _GLASS_APK_CANDIDATES if p.is_file()]
    if not found:
        return None
    return max(found, key=lambda p: p.stat().st_mtime)


def _placeholder_jpeg() -> bytes:
    """Tiny dark JPEG so MJPEG clients stay connected while buffer is empty.

    Built once and cached — never re-run cv2 per connect.
    """
    global _PLACEHOLDER_JPEG
    if _PLACEHOLDER_JPEG is not None:
        return _PLACEHOLDER_JPEG
    try:
        import cv2
        import numpy as np

        img = np.zeros((180, 320, 3), dtype=np.uint8)
        img[:] = (18, 14, 10)
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
        _PLACEHOLDER_JPEG = buf.tobytes() if ok else b""
    except Exception:
        _PLACEHOLDER_JPEG = b""
    return _PLACEHOLDER_JPEG


def _clamp_live_fps(fps: float) -> float:
    return float(min(LIVE_FPS_MAX, max(LIVE_FPS_MIN, fps)))


def _resolve_live_fps(query_fps: float | None = None) -> float:
    """?fps= → clip_buffer.target_fps → DEFAULT_LIVE_FPS; clamped 5–60."""
    if query_fps is not None:
        try:
            return _clamp_live_fps(float(query_fps))
        except (TypeError, ValueError):
            pass
    try:
        from qoresence.vision.clip_buffer import get_clip_buffer

        return _clamp_live_fps(float(get_clip_buffer().target_fps))
    except Exception:
        return _clamp_live_fps(DEFAULT_LIVE_FPS)


def _read_live_jpeg() -> bytes:
    """Latest HDMI JPEG bytes for ``/live.jpg`` / MJPEG.

    Clip-buffer JPEG only. Re-encoding FrameHub BGR on this path caused
    /live.jpg to sit 0.7–2s behind gameplay while snapshot() held the GIL.
    Dark Theater dimming is a Glass ``livePaint`` concern — empty here is 503.
    """
    try:
        from qoresence.vision.clip_buffer import get_latest_frame, get_latest_jpeg

        jpg = get_latest_jpeg()
        if jpg:
            return jpg
        fr = get_latest_frame()
        if fr is not None and fr[0]:
            return fr[0]
    except Exception:
        pass
    return b""


async def _mjpeg_stream(fps: float = DEFAULT_LIVE_FPS):  # type: ignore[no-untyped-def]
    """Async multipart MJPEG — wait for new seq when possible (lower display lag).

    Fixed-rate re-send of the same JPEG made Theater feel "behind" gameplay.
    We poll for a newer seq up to 1/fps, then yield immediately.
    """
    import time as _time

    from qoresence.vision.clip_buffer import get_latest_frame

    fps = _clamp_live_fps(fps)
    boundary = b"frame"
    interval = 1.0 / fps
    dark = _placeholder_jpeg()
    last_seq = -1
    last_jpg = dark
    while True:
        t0 = _time.monotonic()
        jpg: bytes | None = None
        deadline = t0 + interval
        # Wait for a *new* frame instead of sleeping full interval after send
        while True:
            try:
                fr = get_latest_frame()
                if fr is not None:
                    candidate, seq = fr
                    if seq != last_seq:
                        jpg = candidate
                        last_seq = seq
                        break
                else:
                    hub_jpg = _read_live_jpeg()
                    if hub_jpg:
                        jpg = hub_jpg
                        last_seq += 1
                        break
            except Exception:
                pass
            now = _time.monotonic()
            if now >= deadline:
                break
            await asyncio.sleep(min(0.008, deadline - now))
        # Hold the last good JPEG — a dark placeholder flashes LIVE black.
        jpg = jpg or last_jpg or dark
        last_jpg = jpg
        header = (
            b"--" + boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpg)).encode() + b"\r\n"
            b"X-Timestamp: " + f"{_time.time():.3f}".encode() + b"\r\n\r\n"
        )
        yield header + jpg + b"\r\n"


def _mjpeg_generator(fps: float = DEFAULT_LIVE_FPS):  # type: ignore[no-untyped-def]
    """Sync MJPEG for stdlib fallback only (no event loop there)."""
    import time as _time

    fps = _clamp_live_fps(fps)
    boundary = b"frame"
    interval = 1.0 / fps
    dark = _placeholder_jpeg()
    while True:
        t0 = _time.monotonic()
        try:
            jpg = _read_live_jpeg() or dark
        except Exception:
            jpg = dark
        if not jpg:
            jpg = dark
        header = (
            b"--" + boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
        )
        yield header + jpg + b"\r\n"
        elapsed = _time.monotonic() - t0
        sleep = interval - elapsed
        if sleep > 0:
            _time.sleep(sleep)


def create_app():  # type: ignore[no-untyped-def]
    if not _HAS_FASTAPI:
        return None

    try:
        from qoresence.deck.seeing_health import install_health_patch

        install_health_patch()
    except Exception:
        pass

    from fastapi.responses import StreamingResponse

    app = FastAPI(title="Sight Glass", version="0.1.0")
    _gassets = _glass_dist() / "assets"
    if _gassets.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=str(_gassets)), name="glass-assets")

    @app.get("/api/operator/bus")
    def api_operator_bus_get():  # type: ignore[no-untyped-def]
        """Peek operator RCP mailbox. Enqueue-only sibling of A2A — no Retina emit."""
        try:
            from qoresence.operator_bus.mailbox import get_operator_mailbox

            box = get_operator_mailbox()
            return JSONResponse(
                {
                    "ok": True,
                    "schema": "qoresence-operator-bus-1",
                    "plane": "qoresence-observation",
                    "stats": box.stats(),
                    "inbox": box.peek_inbox(20),
                    "outbox": box.peek_outbox(20),
                }
            )
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/api/operator/bus")
    async def api_operator_bus_post(request: Request):  # type: ignore[no-untyped-def]
        """Enqueue one RCP envelope into inbox. Never emit_raw."""
        denied = _local_client_required_response(request)
        if denied is not None:
            return denied
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "json required"}, status_code=400)
        try:
            from qoresence.operator_bus.mailbox import get_operator_mailbox

            env = get_operator_mailbox().enqueue_inbox(body if isinstance(body, dict) else {})
            return JSONResponse({"ok": True, "id": env.id, "envelope": env.to_dict()})
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/operator/bus/prompt")
    def api_operator_bus_prompt():  # type: ignore[no-untyped-def]
        from qoresence.operator_bus.prompt import QOECTOR_BUS_PROMPT

        return JSONResponse(
            {
                "ok": True,
                "from": "grok-build",
                "to": "qorector",
                "prompt": QOECTOR_BUS_PROMPT,
            }
        )

    @app.get("/health")
    def health():  # type: ignore[no-untyped-def]
        gi = _glass_index_path()
        body: dict[str, Any] = {
            "ok": True,
            "schema_version": SCHEMA_VERSION,
            "clients": len(_ws_clients),
            "fanout": _fanout_stats(),
            "state": _state.snapshot(),
            "glass": {
                "js": _glass_js_name(),
                "path": str(gi) if gi is not None else "",
                "clip_dock": True,
            },
        }
        try:
            from qoresence.observability.otel import get_otel_exporter

            _ox = get_otel_exporter()
            if _ox is not None:
                _ostats = _ox.stats()
                _last_ns = _ostats.get("last_export_ns") or 0
                body["otel"] = {
                    "enabled": bool(_ostats.get("enabled")),
                    "exported": int(_ostats.get("exported", 0)),
                    "dropped": int(_ostats.get("dropped", 0)),
                    "last_export_age_s": round(
                        (time.monotonic_ns() - _last_ns) / 1e9, 3
                    )
                    if _last_ns
                    else None,
                    "reentrant_cycles_total": int(
                        _ostats.get("reentrant_cycles_total", 0)
                    ),
                    "reentrant_cycles_recent": int(
                        _ostats.get("reentrant_cycles_recent", 0)
                    ),
                    "reentrant_lobe_counts": _ostats.get(
                        "reentrant_lobe_counts", {}
                    ),
                }
            else:
                body["otel"] = {"enabled": False}
        except Exception:
            body["otel"] = {"enabled": False}
        try:
            from qoresence.a2a.orchestrator import get_a2a_orchestrator

            body["a2a"] = get_a2a_orchestrator().stats()
        except Exception:
            body["a2a"] = {"enabled": False}
        try:
            from qoresence.agents.society import get_society

            soc = get_society()
            body["society"] = soc.stats() if soc is not None else {"enabled": False}
        except Exception:
            body["society"] = {"enabled": False}
        try:
            from qoresence.stem import get_stem_runtime

            _st = get_stem_runtime()
            body["stem"] = _st.health() if _st is not None else {"conductor": False, "mode": None}
        except Exception:
            body["stem"] = {"conductor": False}
        try:
            from qoresence.observability import get_latency_stats

            body["latency"] = get_latency_stats().summary()
        except Exception:
            body["latency"] = {"enabled": False}
        try:
            from qoresence.deck.webrtc_hub import stats as webrtc_stats

            body["webrtc"] = webrtc_stats()
        except Exception:
            body["webrtc"] = {"available": False}
        try:
            from qoresence.sync.ivc import get_last_coupling

            body["coupling"] = get_last_coupling()
        except Exception:
            body["coupling"] = {"imu_bodied": False, "coupling": 0.0, "binds": 0}
        try:
            from qoresence.agents.companion import snapshot_companion

            body["companion"] = snapshot_companion()
        except Exception:
            body["companion"] = {"ok": False, "auto_clip": True, "plane": "qoresence-observation"}
        try:
            from qoresence.agents.actuators import actuators_health

            body["actuators"] = actuators_health(body)
        except Exception:
            body["actuators"] = {"registry": [], "receipts": []}
        try:
            from qoresence.agents.match_agent import surface_last_note

            body["match_agent"] = surface_last_note()
        except Exception:
            body["match_agent"] = {}
        return JSONResponse(body)

    @app.get("/api/situation")
    def api_situation():  # type: ignore[no-untyped-def]
        return JSONResponse(
            _situation_payload(),
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
        )

    @app.get("/live.jpg")
    async def live_jpeg():  # type: ignore[no-untyped-def]
        """Single latest HDMI JPEG — Android WebView cannot play MJPEG.

        Pre-encoded clip-buffer bytes only. Must stay off the snapshot
        threadpool or Theater waits 1s+ behind /health and /api/situation.
        """
        jpg = _read_live_jpeg()
        if not jpg:
            return Response(status_code=503)
        return Response(
            content=jpg,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Access-Control-Allow-Origin": "*",
            },
        )

    @app.websocket("/live")
    async def live_jpeg_ws(websocket: WebSocket):  # type: ignore[no-untyped-def]
        """Push the newest clip-buffer JPEG. Theater must not GET /live.jpg
        per frame — that queued behind the GIL and sat 0.4–1.2s behind HDMI.
        Observation only: read latest bytes, never emit, never take a lobe lock.
        """
        await websocket.accept()
        last_seq = -1
        try:
            from qoresence.vision.clip_buffer import get_latest_frame

            while True:
                fr = None
                try:
                    fr = get_latest_frame()
                except Exception:
                    fr = None
                if fr is not None and fr[0] and fr[1] != last_seq:
                    last_seq = int(fr[1])
                    await websocket.send_bytes(fr[0])
                else:
                    await asyncio.sleep(0.008)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    @app.get("/api/glass-link")
    async def api_glass_link():  # type: ignore[no-untyped-def]
        return JSONResponse({"ok": True, **glass_link_info()})

    @app.get("/api/glass-qr")
    async def api_glass_qr():  # type: ignore[no-untyped-def]
        """SVG QR of the honest glass URL. Empty 204 when localhost-only."""
        info = glass_link_info()
        if not info.get("lan"):
            return Response(status_code=204)
        try:
            from qoresence.deck.glass_qr import url_to_svg

            svg = url_to_svg(str(info["url"]))
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
        return Response(
            content=svg, media_type="image/svg+xml", headers={"Cache-Control": "no-cache"}
        )

    @app.get("/api/discover")
    async def api_discover():  # type: ignore[no-untyped-def]
        """Local mDNS service info — used by the PWA first-run pairing screen."""
        from qoresence.deck.mdns import discovery_info

        return JSONResponse({"ok": True, **discovery_info(_deck_bind_port, _deck_bind_host)})

    @app.get("/glass.apk")
    async def glass_apk():  # type: ignore[no-untyped-def]
        """Sideload the Android cinema APK from the same LAN deck."""
        p = _glass_apk_path()
        if p is None:
            return JSONResponse(
                {"ok": False, "error": "debug APK not built — run native/build-apk.ps1"},
                status_code=404,
            )
        return FileResponse(
            str(p),
            media_type="application/vnd.android.package-archive",
            filename="qoresence-glass-debug.apk",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/manifest.webmanifest")
    async def manifest():  # type: ignore[no-untyped-def]
        p = pathlib.Path(__file__).parent / "manifest.webmanifest"
        if not p.is_file():
            return Response(status_code=404)
        return Response(
            content=p.read_bytes(),
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    @app.get("/sw.js")
    async def service_worker():  # type: ignore[no-untyped-def]
        p = pathlib.Path(__file__).parent / "sw.js"
        if not p.is_file():
            return Response(status_code=404)
        return Response(
            content=p.read_bytes(),
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache, must-revalidate"},
        )

    @app.get("/icons/{name}")
    async def glass_icon(name: str):  # type: ignore[no-untyped-def]
        # Strict allowlist — no path traversal.
        if not name.endswith(".png") or "/" in name or "\\" in name or ".." in name:
            return Response(status_code=404)
        p = pathlib.Path(__file__).parent / "icons" / name
        if not p.is_file():
            return Response(status_code=404)
        return FileResponse(
            str(p), media_type="image/png", headers={"Cache-Control": "public, max-age=3600"}
        )

    @app.get("/fonts/{name}")
    async def glass_font(name: str):  # type: ignore[no-untyped-def]
        # Self-hosted Aperture Glass woff2 for the static shells (Instrument
        # Sans + IBM Plex Mono). No runtime Google Fonts. Strict allowlist.
        if not name.endswith(".woff2") or "/" in name or "\\" in name or ".." in name:
            return Response(status_code=404)
        p = pathlib.Path(__file__).parent / "fonts" / name
        if not p.is_file():
            return Response(status_code=404)
        return FileResponse(
            str(p), media_type="font/woff2", headers={"Cache-Control": "public, max-age=31536000"}
        )

    @app.get("/api/timeline")
    async def api_timeline():  # type: ignore[no-untyped-def]
        """SessionTimeline snapshot — why-last, drives, recent causal events."""
        try:
            from qoresence.agents.session_timeline import get_session_timeline

            return JSONResponse({"ok": True, **get_session_timeline().snapshot()})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/evidence")
    async def api_evidence():  # type: ignore[no-untyped-def]
        """Recent evidence chains and router decisions (Trio P4/P2).

        Reads the JSONL event log and returns the last N evidence_chain
        and router_decision events for the Deck UI evidence panel.
        """
        import json as _json
        from pathlib import Path as _Path

        try:
            jsonl_path = (
                _Path(_state.jsonl_path)
                if hasattr(_state, "jsonl_path")
                else _Path("logs/events.jsonl")
            )
            if not jsonl_path.exists():
                return JSONResponse(
                    {"ok": True, "evidence": [], "router_decisions": [], "count": 0}
                )

            evidence_chains: list[dict] = []
            router_decisions: list[dict] = []
            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()

            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    ev = _json.loads(line)
                except Exception:
                    continue
                et = ev.get("type", "")
                if et == "evidence_chain" and len(evidence_chains) < 10:
                    evidence_chains.append(
                        {
                            "clock_ns": ev.get("clock_ns"),
                            "payload": ev.get("payload"),
                        }
                    )
                elif et == "router_decision" and len(router_decisions) < 20:
                    router_decisions.append(
                        {
                            "clock_ns": ev.get("clock_ns"),
                            "payload": ev.get("payload"),
                        }
                    )
                if len(evidence_chains) >= 10 and len(router_decisions) >= 20:
                    break

            return JSONResponse(
                {
                    "ok": True,
                    "evidence": evidence_chains,
                    "router_decisions": router_decisions,
                    "count": len(evidence_chains),
                }
            )
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/agent/snapshot")
    async def api_agent_snapshot(request: Request):  # type: ignore[no-untyped-def]
        if not _agent_check_token(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        cid = request.client.host if request.client else "unknown"
        try:
            from qoresence.agents.agent_glass import get_agent_glass

            g = get_agent_glass()
            max_eps = (
                float(getattr(getattr(g, "config", None), "max_eps_per_client", 20.0) or 20.0)
                if g and getattr(g, "config", None)
                else 20.0
            )
        except Exception:
            max_eps = 20.0
        if not _agent_eps_ok(cid, max_eps):
            return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=429)
        return JSONResponse(_agent_snapshot_payload(), headers={"Access-Control-Allow-Origin": "*"})

    @app.get("/api/agent/events")
    async def api_agent_events(request: Request):  # type: ignore[no-untyped-def]
        if not _agent_check_token(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        cid = request.client.host if request.client else "unknown"
        try:
            from qoresence.agents.agent_glass import get_agent_glass

            g = get_agent_glass()
            max_eps = (
                float(getattr(getattr(g, "config", None), "max_eps_per_client", 20.0) or 20.0)
                if g and getattr(g, "config", None)
                else 20.0
            )
        except Exception:
            max_eps = 20.0
        if not _agent_eps_ok(cid, max_eps):
            return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=429)
        try:
            since = int(request.query_params.get("since", "0") or 0)
        except Exception:
            since = 0
        types_raw = request.query_params.get("types")
        types = [t.strip() for t in types_raw.split(",") if t.strip()] if types_raw else None
        try:
            limit = int(request.query_params.get("limit", "100") or 100)
        except Exception:
            limit = 100
        try:
            from qoresence.agents.agent_glass import get_agent_glass

            g2 = get_agent_glass()
            if g2 is not None:
                return JSONResponse(
                    g2.get_events(since=since, types=types, limit=limit),
                    headers={"Access-Control-Allow-Origin": "*"},
                )
            return JSONResponse({"ok": True, "events": [], "next_seq": 0, "count": 0})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/agent/health")
    async def api_agent_health(request: Request):  # type: ignore[no-untyped-def]
        if not _agent_check_token(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        try:
            from qoresence.agents.agent_glass import get_agent_glass

            g = get_agent_glass()
            if g is not None:
                return JSONResponse(g.health(), headers={"Access-Control-Allow-Origin": "*"})
            return JSONResponse({"ok": True, "enabled": False, "running": False})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/agent/search")
    async def api_agent_search(request: Request):  # type: ignore[no-untyped-def]
        if not _agent_check_token(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        q = request.query_params.get("query", "") or request.query_params.get("q", "") or ""
        try:
            limit = int(request.query_params.get("limit", "8") or 8)
        except Exception:
            limit = 8
        kinds = request.query_params.get("kinds", "") or ""
        try:
            coupling_min = float(request.query_params.get("coupling_min", "0") or 0)
        except Exception:
            coupling_min = 0.0
        drive_id = request.query_params.get("drive_id", "") or None
        try:
            since_clock_ns = int(request.query_params.get("since_clock_ns", "0") or 0)
        except Exception:
            since_clock_ns = 0
        try:
            from qoresence.foundry.index import search_clips as _sc

            res = _sc(
                query=q,
                limit=limit,
                kinds=kinds,
                coupling_min=coupling_min,
                drive_id=drive_id,
                since_clock_ns=since_clock_ns,
            )
            return JSONResponse(res, headers={"Access-Control-Allow-Origin": "*"})
        except Exception as e:
            return JSONResponse(
                {"ok": False, "error": "search_failed", "hint": str(e)}, status_code=500
            )

    @app.get("/api/agent/graph")
    async def api_agent_graph(request: Request):  # type: ignore[no-untyped-def]
        if not _agent_check_token(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        drive_id = (
            request.query_params.get("drive_id", "") or request.query_params.get("id", "") or None
        )
        inc = (request.query_params.get("include_nodes", "1") or "1").lower() not in (
            "0",
            "false",
            "no",
        )
        try:
            max_nodes = int(request.query_params.get("max_nodes", "40") or 40)
        except Exception:
            max_nodes = 40
        try:
            from qoresence.foundry.index import get_drive_graph as _gdg

            res = _gdg(drive_id=drive_id, include_nodes=inc, max_nodes=max_nodes)
            return JSONResponse(res, headers={"Access-Control-Allow-Origin": "*"})
        except Exception as e:
            return JSONResponse(
                {"ok": False, "error": "drive_graph_failed", "hint": str(e)}, status_code=500
            )

    @app.get("/api/agent/subscribe")
    async def api_agent_subscribe(request: Request):  # type: ignore[no-untyped-def]
        if not _agent_check_token(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        try:
            since = int(request.query_params.get("since", "0") or 0)
        except Exception:
            since = 0
        types = request.query_params.get("types", "") or ""
        try:
            limit = int(request.query_params.get("limit", "20") or 20)
        except Exception:
            limit = 20
        try:
            from qoresence.agents.agent_glass import get_agent_glass

            g2 = get_agent_glass()
            if g2 is not None:
                want = [x.strip() for x in types.split(",") if x.strip()] if types else None
                ev = g2.get_events(since=since, types=want, limit=limit)
                nxt = int(ev.get("next_seq") or since or 0)
                ev["next_since"] = nxt
                ev["poll_again_ms"] = 1000
                return JSONResponse(ev, headers={"Access-Control-Allow-Origin": "*"})
            return JSONResponse(
                {"ok": True, "events": [], "next_seq": 0, "next_since": 0, "count": 0}
            )
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/agent/diagnose")
    async def api_agent_diagnose(request: Request):  # type: ignore[no-untyped-def]
        if not _agent_check_token(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        # Build diagnose in-process from glass / deck state. Do NOT call
        # mcp.handle_diagnose_freeze here — that path HTTP-falls-back to this
        # same server and can self-deadlock the uvicorn event loop.
        try:
            snap = _agent_snapshot_payload()
            video = {}
            coupling = {}
            bus = {}
            seq = 0
            if isinstance(snap, dict) and snap.get("ok"):
                video = snap.get("video") or {}
                coupling = snap.get("coupling") or {}
                bus = snap.get("bus") or {}
                try:
                    seq = int(snap.get("seq") or 0)
                except Exception:
                    seq = 0
                if not video and isinstance(snap.get("state"), dict):
                    video = (snap.get("state") or {}).get("video") or video
            age_s = video.get("age_s") if isinstance(video, dict) else None
            try:
                age_f = float(age_s) if age_s is not None else None
            except Exception:
                age_f = None
            frames = 0
            has_frame = False
            if isinstance(video, dict):
                frames = video.get("frames") or video.get("pushes") or 0
                has_frame = bool(video.get("has_frame"))
            frozen = False
            reasons: list[str] = []
            advice: list[str] = []
            if age_f is not None and age_f > 5.0:
                frozen = True
                reasons.append(f"video.age_s={age_f:.1f}s > 5s - frames stalled")
                advice.append(
                    "not the capture card - capture thread likely deadlocked; "
                    "run py-spy dump --pid <pid>, see AGENTS.md R1/R3/R4"
                )
            if not has_frame and (not frames or int(frames) == 0):
                reasons.append(
                    "no frames yet (has_frame=false, frames=0) - is streamer running? "
                    "(--play --deck --monitor)"
                )
            if seq == 0:
                reasons.append("glass seq=0 - RetinaEventBus not flowing (enable --agent-glass)")
            if not frozen and age_f is not None and age_f < 1.0 and has_frame:
                reasons.append(f"healthy: age_s={age_f:.2f}s, frames={frames}")
            diagnosis = "FROZEN" if frozen else ("NO_FRAMES" if not has_frame else "HEALTHY")
            return JSONResponse(
                {
                    "ok": True,
                    "diagnosis": diagnosis,
                    "frozen": frozen,
                    "healthy": (not frozen and bool(has_frame)),
                    "video": video,
                    "coupling": coupling,
                    "bus": bus,
                    "seq": seq,
                    "age_s": age_f,
                    "has_frame": has_frame,
                    "reasons": reasons,
                    "advice": advice
                    or ["if degraded, lower --streamer-width/height or --streamer-fps 30"],
                    "refs": ["AGENTS.md R1/R3/R4", "docs/AGENT_GLASS.md#threading-invariant"],
                },
                headers={"Access-Control-Allow-Origin": "*"},
            )
        except Exception as e:
            return JSONResponse(
                {"ok": False, "error": "diagnose_failed", "hint": str(e)}, status_code=500
            )

    @app.get("/api/agent/frame")
    async def api_agent_frame(request: Request):  # type: ignore[no-untyped-def]
        if not _agent_check_token(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        try:
            from qoresence.agents.agent_glass import get_agent_glass

            g = get_agent_glass()
            cfg = getattr(g, "config", None) if g else None
            if cfg is not None and not bool(getattr(cfg, "allow_frame", True)):
                return JSONResponse({"ok": False, "error": "frame_disabled"}, status_code=403)
        except Exception:
            pass
        cid = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with _agent_lock:
            last = _agent_frame_last.get(cid, 0.0)
            if now - last < 0.1:
                return JSONResponse({"ok": False, "error": "frame_throttled"}, status_code=429)
            _agent_frame_last[cid] = now
        try:
            from fastapi.responses import Response

            from qoresence.vision.clip_buffer import get_latest_jpeg

            jpg = get_latest_jpeg()
            if not jpg:
                jpg = _placeholder_jpeg()
                if not jpg:
                    return JSONResponse({"ok": False, "error": "no_frame"}, status_code=404)
            return Response(
                content=jpg,
                media_type="image/jpeg",
                headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"},
            )
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/api/agent/clip")
    async def api_agent_clip(request: Request):  # type: ignore[no-untyped-def]
        denied = _local_client_required_response(request)
        if denied is not None:
            return denied
        if not _agent_check_token(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        try:
            from qoresence.agents.agent_glass import get_agent_glass

            g = get_agent_glass()
            cfg = getattr(g, "config", None) if g else None
            if cfg is not None and not bool(getattr(cfg, "allow_clip", True)):
                return JSONResponse({"ok": False, "error": "clip_disabled"}, status_code=403)
        except Exception:
            pass
        global _agent_clip_last
        now = time.monotonic()
        with _agent_lock:
            if now - _agent_clip_last < 10.0:
                return JSONResponse(
                    {
                        "ok": False,
                        "error": "clip_rate_limited",
                        "retry_after_s": round(10.0 - (now - _agent_clip_last), 1),
                    },
                    status_code=429,
                )
            _agent_clip_last = now
        try:
            body: dict = {}
            try:
                body = await request.json()
            except Exception:
                body = {}
            seconds = float(body.get("seconds", 10.0) or 10.0)
            seconds = max(2.0, min(30.0, seconds))
            from qoresence.vision.clip_buffer import get_clip_buffer

            cb = get_clip_buffer()
            res = None
            try:
                res = cb.export_clip(seconds=seconds)  # type: ignore[attr-defined]
            except TypeError:
                try:
                    res = cb.export(seconds=seconds)
                except Exception:
                    res = None
            except Exception:
                res = None
            if res is None:
                # fallback to module-level export_clip
                try:
                    from qoresence.vision.clip_buffer import export_clip

                    res = export_clip(seconds=seconds)
                except Exception:
                    res = None
            if res is None:
                return JSONResponse({"ok": False, "error": "clip_unavailable"}, status_code=503)
            if isinstance(res, dict):
                return JSONResponse(
                    {"ok": True, **res}, headers={"Access-Control-Allow-Origin": "*"}
                )
            try:
                d = dict(res.__dict__)
                return JSONResponse({"ok": True, **d}, headers={"Access-Control-Allow-Origin": "*"})
            except Exception:
                return JSONResponse(
                    {"ok": True, "result": str(res)}, headers={"Access-Control-Allow-Origin": "*"}
                )
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/video")
    async def live_video(request: Request):  # type: ignore[no-untyped-def]
        """Continuous LIVE HDMI preview from clip_buffer JPEG ring (MJPEG fallback).

        Prefer WebRTC: POST /api/webrtc/offer (FrameHub track, no second capture).
        Query: ?fps=60 (default) or ?fps=30 for lighter MJPEG (clamped 5–60).
        """
        qfps = None
        try:
            raw = request.query_params.get("fps")
            if raw is not None and str(raw).strip() != "":
                qfps = float(raw)
        except (TypeError, ValueError):
            qfps = None
        fps = _resolve_live_fps(qfps)
        return StreamingResponse(
            _mjpeg_stream(fps),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "X-Qoresence-Live-Fps": f"{fps:g}",
            },
        )

    @app.get("/api/webrtc/status")
    async def api_webrtc_status():  # type: ignore[no-untyped-def]
        try:
            from qoresence.deck.webrtc_hub import stats as webrtc_stats

            return JSONResponse({"ok": True, **webrtc_stats()})
        except Exception as e:
            return JSONResponse({"ok": False, "available": False, "error": str(e)})

    @app.post("/api/webrtc/offer")
    async def api_webrtc_offer(request: Request):  # type: ignore[no-untyped-def]
        """Browser RTC offer → answer with FrameHub video track (novel wiring).

        Body: {\"sdp\": \"...\", \"type\": \"offer\", \"fps\": 30, \"max_width\": 960}
        No second DShow open — same FrameHub as Retina Monitor / IVC.
        """
        try:
            from qoresence.deck.webrtc_hub import handle_offer, webrtc_available

            if not webrtc_available():
                return JSONResponse(
                    {
                        "ok": False,
                        "error": 'aiortc not installed — pip install aiortc av  (or pip install -e ".[webrtc]")',
                        "fallback": "/video?fps=60",
                    },
                    status_code=503,
                )
            body = await request.json()
            if not isinstance(body, dict) or not body.get("sdp"):
                return JSONResponse({"ok": False, "error": "expected {sdp, type}"}, status_code=400)
            fps = float(body.get("fps") or 30)
            max_w = int(body.get("max_width") or 960)
            answer = await handle_offer(
                str(body["sdp"]),
                str(body.get("type") or "offer"),
                target_fps=fps,
                max_width=max_w,
            )
            return JSONResponse({"ok": True, **answer, "source": "frame_hub"})
        except Exception as e:
            log.exception("WebRTC offer failed")
            return JSONResponse(
                {"ok": False, "error": str(e), "fallback": "/video?fps=60"},
                status_code=500,
            )

    @app.post("/api/stem/hold")
    async def api_stem_hold(request: Request):  # type: ignore[no-untyped-def]
        """Operator HOLD — silence auto-clip. Conductor observes; does not cut."""
        denied = _local_client_required_response(request)
        if denied is not None:
            return denied
        hold_ms = 60_000.0
        try:
            body = await request.json()
            if isinstance(body, dict) and body.get("until_ms") is not None:
                hold_ms = float(body["until_ms"])
        except Exception:
            pass
        try:
            from qoresence.stem import get_stem_runtime

            rt = get_stem_runtime()
            if rt is None:
                return JSONResponse({"ok": False, "error": "stem off"}, status_code=404)
            import time as _t

            until = hold_ms if hold_ms > 1e12 else (_t.time() * 1000.0 + hold_ms)
            rt.conductor.note_hold_until(until)
            return JSONResponse({"ok": True, "hold_until": until, **rt.conductor.snapshot()})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/api/stem/kill")
    async def api_stem_kill(request: Request):  # type: ignore[no-untyped-def]
        denied = _local_client_required_response(request)
        if denied is not None:
            return denied
        try:
            from qoresence.stem import get_stem_runtime

            rt = get_stem_runtime()
            if rt is None:
                return JSONResponse({"ok": False, "error": "stem off"}, status_code=404)
            rt.conductor.note_kill()
            return JSONResponse({"ok": True, **rt.conductor.snapshot()})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/clip/status")
    async def api_clip_status():  # type: ignore[no-untyped-def]
        try:
            from qoresence.vision.clip_buffer import get_clip_buffer

            stats = await asyncio.to_thread(get_clip_buffer().stats)
            return JSONResponse({"ok": True, "buffer": stats})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/api/clip")
    async def api_clip(request: Request):  # type: ignore[no-untyped-def]
        """Export last N seconds of true HDMI capture to local MP4 (not Twitch Helix)."""
        denied = _local_client_required_response(request)
        if denied is not None:
            return denied
        try:
            from qoresence.vision.clip_buffer import export_clip

            seconds = None
            try:
                body = await request.json()
                if isinstance(body, dict):
                    seconds = body.get("seconds")
            except Exception:
                pass
            try:
                from qoresence.stem import get_stem_runtime

                _rt = get_stem_runtime()
                if _rt is not None:
                    _rt.conductor.note_clip_busy(True)
            except Exception:
                pass
            try:
                result = await asyncio.to_thread(export_clip, seconds=seconds)
            finally:
                try:
                    from qoresence.stem import get_stem_runtime

                    _rt = get_stem_runtime()
                    if _rt is not None:
                        _rt.conductor.note_clip_busy(False)
                except Exception:
                    pass
            if result is None:
                return JSONResponse(
                    {
                        "ok": False,
                        "error": "no frames buffered yet — wait ~5s after HDMI capture starts",
                    },
                    status_code=503,
                )
            clip_name = pathlib.Path(result.path).name
            media_url = f"/media/clips/{clip_name}"
            push_moment(
                {
                    "title": f"HDMI CLIP {result.duration_s:.0f}s",
                    "reason": result.path,
                    "clock": "now",
                    "action": "clip",
                    "icon": "🎬",
                    "path": result.path,
                    "url": media_url,
                    "name": clip_name,
                }
            )
            return JSONResponse(
                {
                    "ok": True,
                    "clip": {
                        "path": result.path,
                        "name": clip_name,
                        "url": media_url,
                        "frames": result.frames,
                        "duration_s": result.duration_s,
                        "width": result.width,
                        "height": result.height,
                        "fps": result.fps,
                        "size_bytes": result.size_bytes,
                        "source": result.source,
                    },
                }
            )
        except Exception as e:
            log.exception("POST /api/clip failed")
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/clips")
    async def api_clips():  # type: ignore[no-untyped-def]
        try:

            def _list_clips() -> list[dict[str, Any]]:
                from qoresence.vision.clip_buffer import DEFAULT_OUT_DIR

                root = pathlib.Path(DEFAULT_OUT_DIR)
                items: list[dict[str, Any]] = []
                if not root.exists():
                    return items
                videos = list(root.glob("hdmi_clip_*.mp4")) + list(
                    root.glob("hdmi_clip_*.avi")
                )
                videos.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                for p in videos[:40]:
                    st = p.stat()
                    items.append(
                        {
                            "name": p.name,
                            "path": str(p.resolve()),
                            "url": f"/media/clips/{p.name}",
                            "size_bytes": st.st_size,
                            "mtime": st.st_mtime,
                        }
                    )
                return items

            items = await asyncio.to_thread(_list_clips)
            return JSONResponse(
                {"ok": True, "clips": items},
                headers={"Access-Control-Allow-Origin": "*"},
            )
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/civif/narrative")
    async def api_civif_narrative(clip: str = ""):  # type: ignore[no-untyped-def]
        def _narrate() -> dict[str, Any]:
            from qoresence.foundry.narrative import narrate_clip as _nc
            from qoresence.vision.clip_buffer import DEFAULT_OUT_DIR

            return _nc(clip=str(clip or ""), clips_dir=DEFAULT_OUT_DIR)

        try:
            body = await asyncio.to_thread(_narrate)
            code = 200 if body.get("ok") else 404
            return JSONResponse(body, status_code=code)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/civif/live")
    async def api_civif_live():  # type: ignore[no-untyped-def]
        from qoresence.mcp.server import handle_civif_live

        try:
            return JSONResponse(handle_civif_live())
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/civif/highlights")
    async def api_civif_highlights(limit: int = 8):  # type: ignore[no-untyped-def]
        def _hi() -> dict[str, Any]:
            from qoresence.foundry.highlights import rank_highlights
            from qoresence.vision.clip_buffer import DEFAULT_OUT_DIR

            return rank_highlights(clips_dir=DEFAULT_OUT_DIR, limit=limit)

        try:
            body = await asyncio.to_thread(_hi)
            return JSONResponse(body)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/civif/query")
    async def api_civif_query(
        min_coupling_score: float = 0.0,
        board_locked_only: bool = False,
        controller_bodied_only: bool = False,
        limit: int = 8,
    ):  # type: ignore[no-untyped-def]
        def _q() -> dict[str, Any]:
            from qoresence.foundry.highlights import get_coupled_clips
            from qoresence.vision.clip_buffer import DEFAULT_OUT_DIR

            return get_coupled_clips(
                min_coupling_score=float(min_coupling_score) or None,
                board_locked_only=bool(board_locked_only),
                controller_bodied_only=bool(controller_bodied_only),
                clips_dir=DEFAULT_OUT_DIR,
                limit=int(limit),
            )

        try:
            body = await asyncio.to_thread(_q)
            return JSONResponse(body)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/media/clips/{name}")
    async def media_clip(name: str):  # type: ignore[no-untyped-def]
        """Stream a local HDMI clip MP4 or sidecar JSON for in-page players."""
        import re

        from qoresence.vision.clip_buffer import DEFAULT_OUT_DIR

        safe = pathlib.Path(name).name
        if safe != name:
            return JSONResponse({"ok": False, "error": "invalid name"}, status_code=400)
        # MP4/AVI or sidecars: foo.chapters.json / foo.buttons.json
        if not re.fullmatch(
            r"hdmi_clip_[\w\-]+(\.(mp4|avi|json)|(\.(chapters|buttons|coupling)\.json))",
            safe,
            flags=re.I,
        ):
            return JSONResponse({"ok": False, "error": "invalid name"}, status_code=400)
        root = pathlib.Path(DEFAULT_OUT_DIR).resolve()
        path = (root / safe).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return JSONResponse({"ok": False, "error": "invalid name"}, status_code=400)
        if not path.is_file():
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        suf = path.suffix.lower()
        if suf == ".json":
            media = "application/json"
        elif suf == ".mp4":
            media = "video/mp4"
        else:
            media = "video/x-msvideo"
        return FileResponse(
            path,
            media_type=media,
            content_disposition_type="inline",
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache",
                "Access-Control-Allow-Origin": "*",
                "Content-Disposition": f'inline; filename="{safe}"',
            },
        )

    @app.get("/api/jaeger/{path:path}")
    async def api_jaeger_proxy(path: str):  # type: ignore[no-untyped-def]
        """Proxy to the local Jaeger API so the trace viewer avoids CORS."""
        try:
            import requests

            base = getattr(_deck_config, "jaeger_api_base", "http://127.0.0.1:16686")
            url = f"{base.rstrip('/')}/api/{path}"
            r = requests.get(url, timeout=10)
            return Response(
                content=r.content,
                status_code=r.status_code,
                media_type=r.headers.get("content-type", "application/json"),
                headers={"Access-Control-Allow-Origin": "*"},
            )
        except Exception as e:
            log.exception("GET /api/jaeger failed")
            return JSONResponse({"ok": False, "error": str(e)}, status_code=502)

    @app.get("/api/foundry/status")
    async def api_foundry_status():  # type: ignore[no-untyped-def]
        """Studio enablement + key presence. Never blocks capture."""
        try:
            from qoresence.studio.api import status_payload

            return JSONResponse(status_payload(_deck_config))
        except Exception as e:
            log.exception("GET /api/foundry/status failed")
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/foundry/candidates")
    async def api_foundry_candidates(request: Request):  # type: ignore[no-untyped-def]
        """Ranked chaptered clips for Foundry Bay."""
        try:
            from qoresence.studio.api import list_candidates

            qp = request.query_params if hasattr(request, "query_params") else {}
            limit = 8
            kinds = None
            try:
                limit = int(qp.get("limit") or 8)
            except (TypeError, ValueError):
                limit = 8
            kinds = qp.get("kinds") or None
            items = await asyncio.to_thread(list_candidates, limit, kinds)
            return JSONResponse({"ok": True, "candidates": items})
        except Exception as e:
            log.exception("GET /api/foundry/candidates failed")
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/api/foundry/render")
    async def api_foundry_render(request: Request):  # type: ignore[no-untyped-def]
        """Queue one or more local Ghost Cuts."""
        denied = _local_client_required_response(request)
        if denied is not None:
            return denied
        try:
            from qoresence.studio.api import queue_renders

            cfg = _deck_config
            if cfg is None:
                return JSONResponse({"ok": False, "error": "no config"}, status_code=500)
            if not getattr(cfg, "studio", None) or not cfg.studio.enabled:
                return JSONResponse(
                    {"ok": False, "error": "studio not enabled — start with --studio"},
                    status_code=400,
                )
            body = await request.json() if hasattr(request, "json") else {}
            if not isinstance(body, dict):
                body = {}
            jobs = await asyncio.to_thread(
                queue_renders,
                cfg,
                clip=body.get("clip") or None,
                count=body.get("count"),
                kinds=body.get("kinds") or None,
                style=body.get("style") or None,
            )
            return JSONResponse(
                {
                    "ok": True,
                    "queued": len(jobs),
                    "job_ids": [j.job_id for j in jobs if j.job_id],
                }
            )
        except Exception as e:
            log.exception("POST /api/foundry/render failed")
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/api/foundry/jobs")
    async def api_foundry_jobs():  # type: ignore[no-untyped-def]
        """List recent Ghost Cut jobs."""
        try:
            from qoresence.studio.api import jobs_payload

            jobs = await asyncio.to_thread(jobs_payload, 50)
            return JSONResponse({"ok": True, "jobs": jobs})
        except Exception as e:
            log.exception("GET /api/foundry/jobs failed")
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/media/reels/{name}")
    async def media_reel(name: str):  # type: ignore[no-untyped-def]
        """Stream a Ghost Cut MP4 or receipt."""
        import re

        from qoresence.vision.clip_buffer import DEFAULT_OUT_DIR

        safe = pathlib.Path(name).name
        if not re.fullmatch(r"reel_[\w\-]+(\.(mp4|receipt\.json))", safe, flags=re.I):
            return JSONResponse({"ok": False, "error": "invalid name"}, status_code=400)
        root = pathlib.Path(DEFAULT_OUT_DIR)
        # Search recursively under clips/*_cut/ for the highlight.
        candidates = list(root.rglob(safe))
        if not candidates:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        path = candidates[0]
        media = "video/mp4" if path.suffix == ".mp4" else "application/json"
        return FileResponse(
            path,
            media_type=media,
            filename=safe,
            headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"},
        )

    @app.get("/overlay.html")
    async def overlay():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("overlay.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/obs-live.html")
    async def obs_live():  # type: ignore[no-untyped-def]
        # Pattern B HDMI pixels for OBS CEF — not glass SPA, not raw /video.
        return HTMLResponse(
            _html("obs-live.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/clip-dock.js")
    async def clip_dock_js():  # type: ignore[no-untyped-def]
        p = pathlib.Path(__file__).with_name(_CLIP_DOCK_JS)
        return FileResponse(
            p,
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    @app.get("/clip-dock.css")
    async def clip_dock_css():  # type: ignore[no-untyped-def]
        p = pathlib.Path(__file__).with_name(_CLIP_DOCK_CSS)
        return FileResponse(
            p,
            media_type="text/css",
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    @app.get("/deck.html")
    async def deck():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("deck.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/trace.html")
    async def trace_viewer():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("trace.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/trace")
    async def trace_viewer_alias():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("trace.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/studio.html")
    async def studio():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("studio.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/studio")
    async def studio_alias():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("studio.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/civif.html")
    async def civif_page():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("civif.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/civif")
    async def civif_alias():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("civif.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/session.html")
    async def session_page():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("session.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/session")
    async def session_alias():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("session.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/session.js")
    async def session_js():  # type: ignore[no-untyped-def]
        p = pathlib.Path(__file__).with_name("session.js")
        return FileResponse(
            p,
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    @app.get("/session.css")
    async def session_css():  # type: ignore[no-untyped-def]
        p = pathlib.Path(__file__).with_name("session.css")
        return FileResponse(
            p,
            media_type="text/css",
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    @app.get("/session_fixtures/{name}")
    async def session_fixture(name: str):  # type: ignore[no-untyped-def]
        from qoresence.foundry.session_view import fixture_stem

        stem = fixture_stem(name)
        if stem is None:
            return Response(status_code=404)
        p = pathlib.Path(__file__).with_name("session_fixtures") / f"{stem}.json"
        if not p.is_file():
            return Response(status_code=404)
        return FileResponse(
            p,
            media_type="application/json",
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    @app.get("/api/session/view")
    async def api_session_view(fixture: str = "", session_id: str = ""):  # type: ignore[no-untyped-def]
        # Inline like /health — a thread-pool hop queued behind clip/civif and starved Theater.
        from qoresence.foundry.session_view import build_session_response

        try:
            body = build_session_response(
                session_id=session_id, fixture=fixture, live_situation=_state.situation
            )
        except Exception:
            body = build_session_response(session_id="")
        return JSONResponse(body)

    @app.get("/api/session/recap")
    async def api_session_recap(fixture: str = "", session_id: str = ""):  # type: ignore[no-untyped-def]
        from qoresence.foundry.session_view import build_session_recap

        try:
            body = build_session_recap(
                session_id=session_id, fixture=fixture, live_situation=_state.situation
            )
        except Exception:
            body = build_session_recap(session_id="")
        return JSONResponse(body)

    @app.get("/mobile.html")
    async def mobile_glass():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("mobile.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/glass")
    async def mobile_glass_alias():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("mobile.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/favicon.svg")
    async def glass_favicon():  # type: ignore[no-untyped-def]
        p = _glass_dist() / "favicon.svg"
        if p.is_file():
            return FileResponse(p, media_type="image/svg+xml")
        return Response(status_code=404)

    @app.get("/")
    async def index():  # type: ignore[no-untyped-def]
        if _glass_index_path() is not None:
            return HTMLResponse(
                _html("index.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
            )
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>Sight Glass</title>"
            "<body style='font:14px/1.5 system-ui;background:#0a0e14;color:#e8edf0;padding:24px'>"
            "<h1 style='color:#f5c542'>Sight Glass</h1>"
            "<p><a href='/overlay.html' style='color:#f5c542'>Lens</a> · "
            "<a href='/deck.html' style='color:#f5c542'>Rail</a> · "
            "<a href='/studio.html' style='color:#f5c542'>Foundry Bay</a> · "
            "<a href='/civif.html' style='color:#f5c542'>CIVIF</a> · "
            "<a href='/session.html' style='color:#f5c542'>Session</a> · "
            "<a href='/mobile.html' style='color:#f5c542'>Mobile glass</a> · "
            "<a href='/health' style='color:#f5c542'>health</a> · "
            "<a href='/api/situation' style='color:#f5c542'>api</a></p>"
            "<h2>OBS Browser Source</h2>"
            "<ol>"
            "<li>Sources → <b>+</b> → <b>Browser</b></li>"
            "<li><b>URL</b> (not file://): "
            "<code style='background:#1a2030;padding:2px 8px;border-radius:4px'>"
            "http://127.0.0.1:8765/overlay.html</code></li>"
            "<li>Size <b>1920×1080</b> · Shutdown when not visible <b>OFF</b> · "
            "Refresh when scene active <b>ON</b></li>"
            "<li>Layer <b>above</b> Video Capture (HDMI PS5); background is transparent</li>"
            "<li>Check <code>/health</code> → <code>clients &gt;= 1</code></li>"
            "</ol>"
            "<p style='opacity:.7'>file:///…/overlay.html → WS fail → FIN_WAIT_2 + clients:0. "
            "Test in Edge first, then Refresh OBS source.</p>"
            "</body>"
        )

    @app.websocket("/agent/stream")
    async def agent_ws(websocket: WebSocket):  # type: ignore[no-untyped-def]
        # read-only agent feed: snapshot on connect, then push new events
        # token check via query ?token= or header — optional
        try:
            qp = websocket.query_params.get("token") if hasattr(websocket, "query_params") else None
            auth = (
                websocket.headers.get("authorization", "") if hasattr(websocket, "headers") else ""
            )
            bearer = (qp or auth.replace("Bearer ", "").replace("bearer ", "")).strip()
            from qoresence.agents.agent_glass import get_agent_glass as _gag

            g = _gag()
            cfg = getattr(g, "config", None) if g else None
            if cfg and bool(getattr(cfg, "require_token", False)):
                exp = (
                    pathlib.Path(getattr(cfg, "token_file", ".secrets/agent_glass.token"))
                    .read_text(encoding="utf-8")
                    .strip()
                    .split()[0]
                    if pathlib.Path(
                        getattr(cfg, "token_file", ".secrets/agent_glass.token")
                    ).exists()
                    else ""
                )
                if not bearer or bearer != exp:
                    await websocket.close(code=1008)
                    return
        except Exception:
            pass
        await websocket.accept()
        try:
            await websocket.send_text(json.dumps(_agent_snapshot_payload()))
        except Exception:
            pass
        # subscribe to bus and forward events (rate limited by bus)
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        unsub = None
        try:
            from qoresence.agents.agent_glass import get_agent_glass

            g = get_agent_glass()
            bus = getattr(g, "bus", None) if g else None
            if bus is not None and hasattr(bus, "subscribe"):

                def _fwd(ev):  # type: ignore[no-untyped-def]
                    try:
                        d = (
                            ev.to_dict()
                            if hasattr(ev, "to_dict")
                            else dict(ev)
                            if isinstance(ev, dict)
                            else {"payload": getattr(ev, "payload", {})}
                        )
                        queue.put_nowait(d)
                    except Exception:
                        pass

                try:
                    unsub = bus.subscribe(_fwd)
                except Exception:
                    unsub = None
            # pump
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=1.0)
                    await websocket.send_text(json.dumps(ev))
                except TimeoutError:
                    # keepalive ping with snapshot at snapshot_hz
                    try:
                        payload = await asyncio.to_thread(_agent_snapshot_payload)
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "agent_keepalive",
                                    "payload": payload,
                                    "clock_ns": time.monotonic_ns(),
                                }
                            )
                        )
                    except Exception:
                        break
                except WebSocketDisconnect:
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            if callable(unsub):
                try:
                    unsub()
                except Exception:
                    pass
            try:
                await websocket.close()
            except Exception:
                pass

    @app.websocket(WS_PATH)
    async def retina_ws(websocket: WebSocket):  # type: ignore[no-untyped-def]
        # Param MUST type as module-global WebSocket (see import note above).
        # OBS CEF Browser Source connects here; 403 = clients stays 0 (FIN_WAIT_2 thrash).
        global _loop, _ws_client_count
        await websocket.accept()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_BROADCAST_QUEUE_SIZE)
        with _broadcast_lock:
            _ws_clients.add(websocket)
            _ws_queues[websocket] = queue
            _ws_client_count += 1
        _loop = asyncio.get_running_loop()
        log.info("Deck WS client connected (%d total)", len(_ws_clients))
        sender = asyncio.create_task(_send_deck_queue(websocket, queue))
        try:
            queue.put_nowait(json.dumps(_state.snapshot(), separators=(",", ":")))
            while True:
                # receive() accepts text + binary pings; receive_text() alone can
                # disconnect OBS on non-text frames.
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            sender.cancel()
            try:
                await sender
            except asyncio.CancelledError:
                pass
            with _broadcast_lock:
                _ws_clients.discard(websocket)
                _ws_queues.pop(websocket, None)
                _ws_client_count = max(0, _ws_client_count - 1)
            log.info("Deck WS client gone (%d total)", len(_ws_clients))

    return app


# ---------------------------------------------------------------------------
# stdlib fallback (no fastapi)
# ---------------------------------------------------------------------------


def _run_stdlib(host: str = DECK_HOST, port: int = DECK_PORT) -> None:
    global _deck_bind_host, _deck_bind_port
    _deck_bind_host = str(host or DECK_HOST)
    _deck_bind_port = int(port or DECK_PORT)
    import http.server
    import socketserver

    root = pathlib.Path(__file__).parent

    class H(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):  # type: ignore[no-untyped-def]
            path_only = self.path.split("?", 1)[0]
            if path_only.startswith("/assets/"):
                rel = path_only[len("/assets/") :].replace("\\", "/")
                parts = [p for p in rel.split("/") if p and p not in (".", "..")]
                fp = (_glass_dist() / "assets").joinpath(*parts)
                try:
                    resolved = fp.resolve()
                    root = _glass_dist().resolve()
                    if root not in resolved.parents:
                        raise ValueError("escape")
                except Exception:
                    self.send_response(404)
                    self.end_headers()
                    return
                if resolved.is_file():
                    data = resolved.read_bytes()
                    ctype = {
                        ".js": "application/javascript",
                        ".css": "text/css",
                        ".svg": "image/svg+xml",
                        ".map": "application/json",
                    }.get(resolved.suffix, "application/octet-stream")
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_response(404)
                self.end_headers()
                return
            if path_only in (
                "/",
                "/index.html",
                "/deck.html",
                "/overlay.html",
                "/studio.html",
                "/studio",
                "/mobile.html",
                "/glass",
            ):
                gi = _glass_index_path()
                if gi is not None:
                    data = gi.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache, must-revalidate")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b'<a href="/overlay.html">Lens</a> | <a href="/deck.html">Rail</a>'
                    b' | <a href="/studio.html">Foundry Bay</a>'
                    b' | <a href="/mobile.html">Mobile glass</a>'
                    b' | <a href="/video">LIVE /video</a>'
                )
                return
            if self.path == "/video" or self.path.startswith("/video?"):
                qfps = None
                if "?" in self.path:
                    from urllib.parse import parse_qs, urlparse

                    qs = parse_qs(urlparse(self.path).query)
                    if "fps" in qs and qs["fps"]:
                        try:
                            qfps = float(qs["fps"][0])
                        except (TypeError, ValueError):
                            qfps = None
                fps = _resolve_live_fps(qfps)
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-cache, no-store")
                self.send_header("X-Qoresence-Live-Fps", f"{fps:g}")
                self.end_headers()
                try:
                    for chunk in _mjpeg_generator(fps):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return
                return
            if self.path in ("/studio.html", "/studio"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, must-revalidate")
                self.end_headers()
                self.wfile.write(_html("studio.html").encode("utf-8"))
                return
            if self.path == "/obs-live.html" or self.path.startswith("/obs-live.html?"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, must-revalidate")
                self.end_headers()
                self.wfile.write(_html("obs-live.html").encode("utf-8"))
                return
            if self.path in ("/mobile.html", "/glass"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, must-revalidate")
                self.end_headers()
                self.wfile.write(_html("mobile.html").encode("utf-8"))
                return
            if self.path == "/api/glass-link":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, **glass_link_info()}).encode())
                return
            if self.path == "/api/discover":
                from qoresence.deck.mdns import discovery_info

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"ok": True, **discovery_info(_deck_bind_port, _deck_bind_host)}
                    ).encode()
                )
                return
            if self.path == "/glass.apk":
                _apk = _glass_apk_path()
                if _apk is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                data = _apk.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.android.package-archive")
                self.send_header(
                    "Content-Disposition", 'attachment; filename="qoresence-glass-debug.apk"'
                )
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data)
                return
            if self.path == "/manifest.webmanifest":
                _p = root / "manifest.webmanifest"
                if _p.is_file():
                    self.send_response(200)
                    self.send_header("Content-Type", "application/manifest+json")
                    self.send_header("Cache-Control", "no-cache, must-revalidate")
                    self.end_headers()
                    self.wfile.write(_p.read_bytes())
                else:
                    self.send_response(404)
                    self.end_headers()
                return
            if self.path == "/sw.js":
                _p = root / "sw.js"
                if _p.is_file():
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript")
                    self.send_header("Service-Worker-Allowed", "/")
                    self.send_header("Cache-Control", "no-cache, must-revalidate")
                    self.end_headers()
                    self.wfile.write(_p.read_bytes())
                else:
                    self.send_response(404)
                    self.end_headers()
                return
            if self.path.startswith("/icons/"):
                from urllib.parse import unquote

                _name = unquote(self.path[len("/icons/") :])
                if (
                    _name.endswith(".png")
                    and "/" not in _name
                    and "\\" not in _name
                    and ".." not in _name
                ):
                    _p = root / "icons" / _name
                    if _p.is_file():
                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Cache-Control", "public, max-age=3600")
                        self.end_headers()
                        self.wfile.write(_p.read_bytes())
                        return
                self.send_response(404)
                self.end_headers()
                return
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                health: dict[str, Any] = {"ok": True, "state": _state.snapshot()}
                try:
                    from qoresence.sync.ivc import get_last_coupling

                    health["coupling"] = get_last_coupling()
                except Exception:
                    health["coupling"] = {"imu_bodied": False, "coupling": 0.0, "binds": 0}
                try:
                    from qoresence.observability.otel import get_otel_exporter

                    _ox = get_otel_exporter()
                    if _ox is not None:
                        _ostats = _ox.stats()
                        _last_ns = _ostats.get("last_export_ns") or 0
                        health["otel"] = {
                            "enabled": bool(_ostats.get("enabled")),
                            "exported": int(_ostats.get("exported", 0)),
                            "dropped": int(_ostats.get("dropped", 0)),
                            "last_export_age_s": round(
                                (time.monotonic_ns() - _last_ns) / 1e9, 3
                            )
                            if _last_ns
                            else None,
                            "reentrant_cycles_total": int(
                                _ostats.get("reentrant_cycles_total", 0)
                            ),
                            "reentrant_cycles_recent": int(
                                _ostats.get("reentrant_cycles_recent", 0)
                            ),
                            "reentrant_lobe_counts": _ostats.get(
                                "reentrant_lobe_counts", {}
                            ),
                        }
                    else:
                        health["otel"] = {"enabled": False}
                except Exception:
                    health["otel"] = {"enabled": False}
                try:
                    from qoresence.agents.match_agent import surface_last_note

                    health["match_agent"] = surface_last_note()
                except Exception:
                    health["match_agent"] = {}
                self.wfile.write(json.dumps(health).encode())
                return
            if self.path == "/api/situation":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(json.dumps(_situation_payload()).encode())
                return
            if self.path == "/live.jpg" or self.path.startswith("/live.jpg?"):
                jpg = _read_live_jpeg()
                if not jpg:
                    self.send_response(503)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(jpg)
                return
            if self.path.startswith("/api/agent/snapshot"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(_agent_snapshot_payload()).encode())
                return
            if self.path.startswith("/api/agent/health"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                try:
                    from qoresence.agents.agent_glass import get_agent_glass

                    g = get_agent_glass()
                    payload = g.health() if g else {"ok": True, "enabled": False, "running": False}
                except Exception as e:
                    payload = {"ok": False, "error": str(e)}
                self.wfile.write(json.dumps(payload).encode())
                return
            if self.path.startswith("/api/agent/events"):
                from urllib.parse import parse_qs
                from urllib.parse import urlparse as _urlparse

                qs = parse_qs(_urlparse(self.path).query)
                try:
                    since = int((qs.get("since") or ["0"])[0])
                except Exception:
                    since = 0
                try:
                    limit = int((qs.get("limit") or ["100"])[0])
                except Exception:
                    limit = 100
                types_raw = (qs.get("types") or [None])[0]
                types = (
                    [t.strip() for t in types_raw.split(",") if t.strip()] if types_raw else None
                )
                try:
                    from qoresence.agents.agent_glass import get_agent_glass

                    g = get_agent_glass()
                    payload = (
                        g.get_events(since=since, types=types, limit=limit)
                        if g
                        else {"ok": True, "events": [], "next_seq": 0, "count": 0}
                    )
                except Exception as e:
                    payload = {"ok": False, "error": str(e)}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())
                return
            if self.path.startswith("/api/agent/frame"):
                try:
                    from qoresence.vision.clip_buffer import get_latest_jpeg

                    jpg = get_latest_jpeg() or _placeholder_jpeg()
                    if not jpg:
                        self.send_response(404)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(b'{"ok": false, "error": "no_frame"}')
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(jpg)
                    return
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
                    return
            return super().do_GET()

        def do_POST(self):  # type: ignore[no-untyped-def]
            from qoresence.security.redact import client_host_is_loopback

            if not client_host_is_loopback(self.client_address[0]):
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": false, "error": "local_client_required"}')
                return
            if self.path.startswith("/api/agent/clip"):
                length = int(self.headers.get("Content-Length", 0) or 0)
                body_raw = self.rfile.read(length) if length else b"{}"
                try:
                    body = json.loads(body_raw.decode("utf-8") or "{}")
                except Exception:
                    body = {}
                seconds = float(body.get("seconds", 10.0) or 10.0)
                seconds = max(2.0, min(30.0, seconds))
                try:
                    from qoresence.vision.clip_buffer import export_clip

                    res = export_clip(seconds=seconds)
                    if res is None:
                        self.send_response(503)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(b'{"ok": false, "error": "clip_unavailable"}')
                        return
                    payload = {"ok": True}
                    if isinstance(res, dict):
                        payload.update(res)
                    else:
                        try:
                            payload.update(dict(res.__dict__))
                        except Exception:
                            payload["result"] = str(res)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode())
                    return
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
                    return
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": false, "error": "not found"}')

        def end_headers(self):  # type: ignore[no-untyped-def]
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

    import os

    os.chdir(root)
    # ThreadingTCPServer: each LIVE /video client gets its own thread so
    # health/situation still respond under load (sync generator + sleep).
    with socketserver.ThreadingTCPServer((host, port), H) as httpd:
        httpd.daemon_threads = True
        log.info("Sight Glass (stdlib ThreadingTCPServer) http://%s:%s", host, port)
        httpd.serve_forever()


# ---------------------------------------------------------------------------
# Public runner — called from cli --deck / --play
# ---------------------------------------------------------------------------


def start_deck(
    host: str = DECK_HOST,
    port: int = DECK_PORT,
    daemon: bool = True,
    config: Any = None,
) -> threading.Thread | None:
    global _deck_config, _deck_bind_host, _deck_bind_port
    _deck_config = config
    _deck_bind_host = str(host or DECK_HOST)
    _deck_bind_port = int(port or DECK_PORT)
    try:
        from qoresence.deck.seeing_health import install_health_patch

        install_health_patch()
    except Exception:
        pass
    if config is not None and getattr(config, "studio", None) and config.studio.enabled:
        try:
            from qoresence.studio.api import boot_studio

            boot_studio(config)
        except Exception:
            log.exception("Foundry Bay boot failed")
    # mDNS auto-discovery — LAN only, no-op on loopback or if zeroconf absent.
    # stop_mdns() is registered at exit for clean teardown.
    try:
        from qoresence.deck.mdns import start_mdns

        start_mdns(_deck_bind_port, _deck_bind_host)
    except Exception as e:
        log.debug("mDNS start skipped: %s", e)
    try:
        import atexit

        from qoresence.deck.mdns import stop_mdns

        atexit.register(stop_mdns)
    except Exception:
        pass
    app = create_app()
    if app is not None:
        import uvicorn

        def _run():  # type: ignore[no-untyped-def]
            global _loop, _ws_client_count, _broadcast_scheduled
            with _broadcast_lock:
                _broadcast_pending.clear()
                _broadcast_scheduled = False
                _ws_client_count = 0
                _ws_clients.clear()
                _ws_queues.clear()
            _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)
            uvicorn.run(app, host=host, port=port, log_level="warning")

        t = threading.Thread(target=_run, name="retina-deck", daemon=daemon)
        t.start()
        log.info("Sight Glass http://%s:%s  ws://%s:%s%s", host, port, host, port, WS_PATH)
        log.info("Theater glass %s clip-dock on", _glass_js_name())
        log.info(
            "Lens /overlay.html  HDMI /obs-live.html  Theater /deck.html  Foundry /studio.html  "
            "CIVIF /civif.html  Session /session.html  Mobile /mobile.html  LIVE /video default %.0ffps "
            "(PS5 60 Hz full-rate LIVE default; override ?fps= for lighter)",
            DEFAULT_LIVE_FPS,
        )
        if config is not None and getattr(config, "studio", None) and config.studio.enabled:
            log.info("Foundry Bay http://%s:%s/studio.html (studio enabled)", host, port)
        return t
    # fallback
    t = threading.Thread(
        target=_run_stdlib, args=(host, port), name="retina-deck-stdio", daemon=daemon
    )
    t.start()
    return t
