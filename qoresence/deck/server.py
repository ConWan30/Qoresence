"""Retina Deck — ws://localhost:8765/retina + HTTP overlay/deck.

One brain (RetinaEventBus / SituationModel) -> three glasses:
  A) Clutch Lens  http://localhost:8765/overlay.html  (OBS Browser Source, transparent)
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
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore[misc, assignment]
    Request = None  # type: ignore[misc, assignment]
    WebSocket = None  # type: ignore[misc, assignment]
    WebSocketDisconnect = None  # type: ignore[misc, assignment]
    FileResponse = None  # type: ignore[misc, assignment]
    HTMLResponse = None  # type: ignore[misc, assignment]
    JSONResponse = None  # type: ignore[misc, assignment]
    _HAS_FASTAPI = False

# ---------------------------------------------------------------------------
# State store — updated by RetinaEventBus subscriber (cli wires this)
# ---------------------------------------------------------------------------


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
        controller: dict[str, Any] = {}
        try:
            from qoresence.sync.input_ring import get_input_ring
            from qoresence.sync.ivc import get_ivc, get_last_coupling

            if get_ivc() is not None:
                coup = get_last_coupling()
                controller = {
                    "buttons": get_input_ring().latest_buttons()[:8],
                    "coupling": coup.get("coupling", 0.0),
                    "frame_seq": coup.get("frame_seq", 0),
                    "input_energy": coup.get("input_energy", 0.0),
                }
        except Exception:
            controller = {}
        out: dict[str, Any] = {
            "type": "snapshot",
            "situation": self.situation,
            "last_moment": self.last_moment,
            "moments": self.moments[-3:],
            "latency_ms": self.latency_ms,
            "fps": self.fps,
            "updated_ns": self.updated_ns,
            "video": video,
        }
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
        return out


_state = DeckState()
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

    _state.situation = situation
    _state.updated_ns = _t.monotonic_ns()
    if latency_ms is not None:
        _state.latency_ms = latency_ms
    _broadcast(
        {
            "type": "situation",
            "payload": situation,
            "latency_ms": _state.latency_ms,
            "updated_ns": _state.updated_ns,
        }
    )


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


# ---------------------------------------------------------------------------
# AgentGlass helpers (read-only snapshot for external agents — no capture)
# ---------------------------------------------------------------------------

_agent_frame_last: dict[str, float] = {}
_agent_clip_last: float = 0.0
_agent_eps: dict[str, list[float]] = {}
_agent_lock = threading.Lock()


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
            return g.snapshot()
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


def _html(name: str) -> str:
    p = pathlib.Path(__file__).with_name(name)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return f"<h1>{name} missing</h1>"


_PLACEHOLDER_JPEG: bytes | None = None


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
    """In-memory read of latest HDMI JPEG (brief lock) — safe on event loop."""
    try:
        from qoresence.vision.clip_buffer import get_latest_frame, get_latest_jpeg

        fr = get_latest_frame()
        if fr is not None:
            return fr[0]
        jpg = get_latest_jpeg()
        if jpg:
            return jpg
    except Exception:
        pass
    return _placeholder_jpeg()


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
            except Exception:
                pass
            now = _time.monotonic()
            if now >= deadline:
                # Timeout: still emit latest (or placeholder) to keep connection alive
                try:
                    fr = get_latest_frame()
                    if fr is not None:
                        jpg, last_seq = fr[0], fr[1]
                except Exception:
                    jpg = None
                break
            await asyncio.sleep(min(0.002, deadline - now))
        if not jpg:
            jpg = dark
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

    from fastapi.responses import StreamingResponse

    app = FastAPI(title="Retina Deck", version="0.1.0")

    @app.get("/health")
    async def health():  # type: ignore[no-untyped-def]
        body: dict[str, Any] = {
            "ok": True,
            "clients": len(_ws_clients),
            "fanout": _fanout_stats(),
            "state": _state.snapshot(),
        }
        try:
            from qoresence.a2a.orchestrator import get_a2a_orchestrator

            body["a2a"] = get_a2a_orchestrator().stats()
        except Exception:
            body["a2a"] = {"enabled": False}
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
        return JSONResponse(body)

    @app.get("/api/situation")
    async def api_situation():  # type: ignore[no-untyped-def]
        return JSONResponse(_state.snapshot())

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
        try:
            from qoresence.vision.clip_buffer import export_clip

            seconds = None
            try:
                body = await request.json()
                if isinstance(body, dict):
                    seconds = body.get("seconds")
            except Exception:
                pass
            result = await asyncio.to_thread(export_clip, seconds=seconds)
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
                if root.exists():
                    for p in sorted(
                        root.glob("hdmi_clip_*.*"),
                        key=lambda x: x.stat().st_mtime,
                        reverse=True,
                    )[:40]:
                        items.append(
                            {
                                "name": p.name,
                                "path": str(p.resolve()),
                                "url": f"/media/clips/{p.name}",
                                "size_bytes": p.stat().st_size,
                                "mtime": p.stat().st_mtime,
                            }
                        )
                return items

            items = await asyncio.to_thread(_list_clips)
            return JSONResponse({"ok": True, "clips": items})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/media/clips/{name}")
    async def media_clip(name: str):  # type: ignore[no-untyped-def]
        """Stream a local HDMI clip MP4 or sidecar JSON for in-page players."""
        import re

        from qoresence.vision.clip_buffer import DEFAULT_OUT_DIR

        safe = pathlib.Path(name).name
        # MP4/AVI or sidecars: foo.chapters.json / foo.buttons.json
        if not re.fullmatch(
            r"hdmi_clip_[\w\-]+(\.(mp4|avi|json)|(\.(chapters|buttons)\.json))",
            safe,
            flags=re.I,
        ):
            return JSONResponse({"ok": False, "error": "invalid name"}, status_code=400)
        path = pathlib.Path(DEFAULT_OUT_DIR) / safe
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
            filename=safe,
            headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"},
        )

    @app.get("/overlay.html")
    async def overlay():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("overlay.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/deck.html")
    async def deck():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            _html("deck.html"), headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/")
    async def index():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>Retina Deck</title>"
            "<body style='font:14px/1.5 system-ui;background:#0a0e14;color:#e8edf0;padding:24px'>"
            "<h1 style='color:#f5c542'>Retina Deck</h1>"
            "<p><a href='/overlay.html' style='color:#f5c542'>Lens</a> · "
            "<a href='/deck.html' style='color:#f5c542'>Rail</a> · "
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
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "agent_keepalive",
                                    "payload": _agent_snapshot_payload(),
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
    import http.server
    import socketserver

    root = pathlib.Path(__file__).parent

    class H(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):  # type: ignore[no-untyped-def]
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b'<a href="/overlay.html">Lens</a> | <a href="/deck.html">Rail</a>'
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
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "state": _state.snapshot()}).encode())
                return
            if self.path == "/api/situation":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(_state.snapshot()).encode())
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
        log.info("Retina Deck (stdlib ThreadingTCPServer) http://%s:%s", host, port)
        httpd.serve_forever()


# ---------------------------------------------------------------------------
# Public runner — called from cli --deck / --play
# ---------------------------------------------------------------------------


def start_deck(
    host: str = DECK_HOST, port: int = DECK_PORT, daemon: bool = True
) -> threading.Thread | None:
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
        log.info("Retina Deck http://%s:%s  ws://%s:%s%s", host, port, host, port, WS_PATH)
        log.info(
            "Lens /overlay.html  Theater /deck.html  LIVE /video default %.0ffps "
            "(PS5 60 Hz full-rate LIVE default; override ?fps= for lighter)",
            DEFAULT_LIVE_FPS,
        )
        return t
    # fallback
    t = threading.Thread(
        target=_run_stdlib, args=(host, port), name="retina-deck-stdio", daemon=daemon
    )
    t.start()
    return t
