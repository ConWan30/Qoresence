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
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

DECK_HOST = "127.0.0.1"
DECK_PORT = 8765
WS_PATH = "/retina"
# Ghost Theater LIVE default: half-rate of PS5 60 Hz (smooth, bounded CPU/RAM)
DEFAULT_LIVE_FPS = 30.0
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
        return {
            "type": "snapshot",
            "situation": self.situation,
            "last_moment": self.last_moment,
            "moments": self.moments[-3:],
            "latency_ms": self.latency_ms,
            "fps": self.fps,
            "updated_ns": self.updated_ns,
            "video": video,
        }


_state = DeckState()
_ws_clients: set[Any] = set()
_loop: asyncio.AbstractEventLoop | None = None


def update_situation(situation: dict[str, Any], latency_ms: float | None = None) -> None:
    # Reject stale/empty payloads — live feed must have at least one real field
    if not situation or not any(situation.get(k) is not None for k in ("home_score", "away_score", "quarter", "down", "kills", "health", "game_state", "score_home")):
        return
    import time as _t
    _state.situation = situation
    _state.updated_ns = _t.monotonic_ns()
    if latency_ms is not None:
        _state.latency_ms = latency_ms
    _broadcast({"type": "situation", "payload": situation, "latency_ms": _state.latency_ms, "updated_ns": _state.updated_ns})


def push_moment(moment: dict[str, Any]) -> None:
    # Only allow live-triggered moments (must have title)
    if not moment or not moment.get("title"):
        return
    import time as _t
    moment = dict(moment)
    moment.setdefault("ts_ns", _t.monotonic_ns())
    _state.last_moment = moment
    _state.moments.append(moment)
    if len(_state.moments) > 100:
        _state.moments = _state.moments[-100:]
    _broadcast({"type": "moment", "payload": moment})


def _broadcast(msg: dict[str, Any]) -> None:
    if _loop is None or not _ws_clients:
        return
    data = json.dumps(msg)
    for ws in list(_ws_clients):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(data), _loop)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# FastAPI app (preferred)
# ---------------------------------------------------------------------------


def _html(name: str) -> str:
    p = pathlib.Path(__file__).with_name(name)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return f"<h1>{name} missing</h1>"


def _placeholder_jpeg() -> bytes:
    """Tiny dark JPEG so MJPEG clients stay connected while buffer is empty."""
    import cv2
    import numpy as np

    img = np.zeros((180, 320, 3), dtype=np.uint8)
    img[:] = (18, 14, 10)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
    return buf.tobytes() if ok else b""


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


def _mjpeg_generator(fps: float = DEFAULT_LIVE_FPS):  # type: ignore[no-untyped-def]
    """Yield multipart MJPEG from clip_buffer at paced fps (default 30 = PS5/2)."""
    import time as _time

    from qoresence.vision.clip_buffer import get_latest_frame, get_latest_jpeg

    fps = _clamp_live_fps(fps)
    boundary = b"frame"
    interval = 1.0 / fps
    dark = _placeholder_jpeg()
    last_seq = -1
    while True:
        t0 = _time.monotonic()
        jpg: bytes | None = None
        try:
            fr = get_latest_frame()
            if fr is not None:
                jpg, seq = fr
                # Prefer newest seq; still re-yield same frame if stalled so
                # multipart stays alive (no busy loop — we always sleep).
                if seq != last_seq:
                    last_seq = seq
            if not jpg:
                jpg = get_latest_jpeg()
        except Exception:
            jpg = None
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
        return JSONResponse({"ok": True, "clients": len(_ws_clients), "state": _state.snapshot()})

    @app.get("/api/situation")
    async def api_situation():  # type: ignore[no-untyped-def]
        return JSONResponse(_state.snapshot())

    @app.get("/video")
    async def live_video(request: Request):  # type: ignore[no-untyped-def]
        """Continuous LIVE HDMI preview from clip_buffer JPEG ring (MJPEG).

        Query: ?fps=30 (default) or ?fps=60 for full-rate preview (clamped 5–60).
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
            _mjpeg_generator(fps),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "X-Qoresence-Live-Fps": f"{fps:g}",
            },
        )

    @app.get("/api/clip/status")
    async def api_clip_status():  # type: ignore[no-untyped-def]
        try:
            from qoresence.vision.clip_buffer import get_clip_buffer

            return JSONResponse({"ok": True, "buffer": get_clip_buffer().stats()})
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
            from qoresence.vision.clip_buffer import DEFAULT_OUT_DIR

            root = pathlib.Path(DEFAULT_OUT_DIR)
            items = []
            if root.exists():
                for p in sorted(root.glob("hdmi_clip_*.*"), key=lambda x: x.stat().st_mtime, reverse=True)[:40]:
                    items.append(
                        {
                            "name": p.name,
                            "path": str(p.resolve()),
                            "url": f"/media/clips/{p.name}",
                            "size_bytes": p.stat().st_size,
                            "mtime": p.stat().st_mtime,
                        }
                    )
            return JSONResponse({"ok": True, "clips": items})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/media/clips/{name}")
    async def media_clip(name: str):  # type: ignore[no-untyped-def]
        """Stream a local HDMI clip MP4 for in-page / browser video players."""
        import re

        from qoresence.vision.clip_buffer import DEFAULT_OUT_DIR

        safe = pathlib.Path(name).name
        if not re.fullmatch(r"hdmi_clip_[\w.\-]+", safe):
            return JSONResponse({"ok": False, "error": "invalid name"}, status_code=400)
        path = pathlib.Path(DEFAULT_OUT_DIR) / safe
        if not path.is_file():
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        media = "video/mp4" if path.suffix.lower() == ".mp4" else "video/x-msvideo"
        return FileResponse(
            path,
            media_type=media,
            filename=safe,
            headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"},
        )

    @app.get("/overlay.html")
    async def overlay():  # type: ignore[no-untyped-def]
        return HTMLResponse(_html("overlay.html"))

    @app.get("/deck.html")
    async def deck():  # type: ignore[no-untyped-def]
        return HTMLResponse(_html("deck.html"))

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

    @app.websocket(WS_PATH)
    async def retina_ws(websocket: WebSocket):  # type: ignore[no-untyped-def]
        # Param MUST type as module-global WebSocket (see import note above).
        # OBS CEF Browser Source connects here; 403 = clients stays 0 (FIN_WAIT_2 thrash).
        global _loop
        await websocket.accept()
        _ws_clients.add(websocket)
        _loop = asyncio.get_running_loop()
        log.info("Deck WS client connected (%d total)", len(_ws_clients))
        await websocket.send_text(json.dumps(_state.snapshot()))
        try:
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
            _ws_clients.discard(websocket)
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
            return super().do_GET()

        def end_headers(self):  # type: ignore[no-untyped-def]
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

    import os

    os.chdir(root)
    with socketserver.TCPServer((host, port), H) as httpd:
        log.info("Retina Deck (stdlib) http://%s:%s", host, port)
        httpd.serve_forever()


# ---------------------------------------------------------------------------
# Public runner — called from cli --deck / --play
# ---------------------------------------------------------------------------


def start_deck(
    host: str = DECK_HOST, port: int = DECK_PORT, daemon: bool = True
) -> threading.Thread | None:
    app = create_app()
    if app is not None:
        import uvicorn  # type: ignore[import-not-found]

        def _run():  # type: ignore[no-untyped-def]
            global _loop
            _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)
            uvicorn.run(app, host=host, port=port, log_level="warning")

        t = threading.Thread(target=_run, name="retina-deck", daemon=daemon)
        t.start()
        log.info("Retina Deck http://%s:%s  ws://%s:%s%s", host, port, host, port, WS_PATH)
        log.info(
            "Lens /overlay.html  Theater /deck.html  LIVE /video default %.0ffps "
            "(PS5 60 Hz half-rate; override ?fps= up to 60)",
            DEFAULT_LIVE_FPS,
        )
        return t
    # fallback
    t = threading.Thread(
        target=_run_stdlib, args=(host, port), name="retina-deck-stdio", daemon=daemon
    )
    t.start()
    return t
