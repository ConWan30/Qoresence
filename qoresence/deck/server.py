"""Retina Deck — load canonical server, then mount the Recap notary door.

The previous commit accidentally replaced this module. We reload the last
good implementation (main 7b60a836) and wrap create_app so Session Theater
gets /api/session/clock-notary* plus /session-door.js.
"""

from __future__ import annotations

import pathlib
import runpy
import urllib.request

_HERE = pathlib.Path(__file__).resolve()
_CACHE = _HERE.with_name("_server_canon.py")
_CANON = (
    "https://raw.githubusercontent.com/ConWan30/Qoresence/"
    "7b60a836f54bb4509b3b422ff487739dbb599732/qoresence/deck/server.py"
)


def _ensure_canon() -> pathlib.Path:
    if _CACHE.is_file() and _CACHE.stat().st_size > 10_000:
        return _CACHE
    with urllib.request.urlopen(_CANON, timeout=30) as resp:
        _CACHE.write_bytes(resp.read())
    return _CACHE


_ns = runpy.run_path(str(_ensure_canon()), run_name="qoresence.deck._server_canon")
_orig_create_app = _ns["create_app"]


def create_app():  # type: ignore[no-untyped-def]
    app = _orig_create_app()
    from qoresence.deck.clock_notary_http import mount_clock_notary

    mount_clock_notary(app, lambda: _ns["_state"].situation)
    FileResponse = _ns.get("FileResponse")
    if FileResponse is not None:

        @app.get("/session-door.js")
        async def session_door_js():  # type: ignore[no-untyped-def]
            p = _HERE.with_name("session-door.js")
            return FileResponse(
                p,
                media_type="text/javascript",
                headers={"Cache-Control": "no-cache, must-revalidate"},
            )

    return app


_ns["create_app"] = create_app
globals().update({k: v for k, v in _ns.items() if k not in {"create_app", "__name__", "__file__"}})
