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

    def snapshot(self) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "situation": self.situation,
            "last_moment": self.last_moment,
            "moments": self.moments[-3:],
            "latency_ms": self.latency_ms,
            "fps": self.fps,
        }


_state = DeckState()
_ws_clients: set[Any] = set()
_loop: asyncio.AbstractEventLoop | None = None


def update_situation(situation: dict[str, Any], latency_ms: float | None = None) -> None:
    _state.situation = situation
    if latency_ms is not None:
        _state.latency_ms = latency_ms
    _broadcast({"type": "situation", "payload": situation, "latency_ms": _state.latency_ms})


def push_moment(moment: dict[str, Any]) -> None:
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


def create_app():  # type: ignore[no-untyped-def]
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse, JSONResponse
    except ImportError:
        return None

    app = FastAPI(title="Retina Deck", version="0.1.0")

    @app.get("/health")
    async def health():  # type: ignore[no-untyped-def]
        return JSONResponse({"ok": True, "clients": len(_ws_clients), "state": _state.snapshot()})

    @app.get("/api/situation")
    async def api_situation():  # type: ignore[no-untyped-def]
        return JSONResponse(_state.snapshot())

    @app.get("/overlay.html")
    async def overlay():  # type: ignore[no-untyped-def]
        return HTMLResponse(_html("overlay.html"))

    @app.get("/deck.html")
    async def deck():  # type: ignore[no-untyped-def]
        return HTMLResponse(_html("deck.html"))

    @app.get("/")
    async def index():  # type: ignore[no-untyped-def]
        return HTMLResponse(
            '<a href="/overlay.html">Lens</a> | <a href="/deck.html">Rail</a> | <a href="/health">health</a>'
        )

    @app.websocket(WS_PATH)
    async def retina_ws(ws: WebSocket):  # type: ignore[no-untyped-def]
        global _loop
        await ws.accept()
        _ws_clients.add(ws)
        _loop = asyncio.get_running_loop()
        await ws.send_text(json.dumps(_state.snapshot()))
        try:
            while True:
                await ws.receive_text()  # keepalive / client pings
        except WebSocketDisconnect:
            pass
        finally:
            _ws_clients.discard(ws)

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
                )
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
        return t
    # fallback
    t = threading.Thread(
        target=_run_stdlib, args=(host, port), name="retina-deck-stdio", daemon=daemon
    )
    t.start()
    return t
