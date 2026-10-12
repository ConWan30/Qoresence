"""Read-only Deck endpoints for the truth feed (FastAPI + stdlib fallback).

    GET /api/truth/feed     recent facts (?since=<seq>&limit=<n>)
    GET /api/truth/stream   Server-Sent Events (?since=<seq>&limit_s=<seconds>)
    GET /api/truth/verify   re-verify the session file (chain + signatures)
    GET /api/truth/pubkey   public key + key id (never the private key)

Access: loopback clients only, unless ``QORESENCE_TRUTH_FEED_LAN=1`` opts the
endpoints into LAN reads. The existing Agent Glass bearer token
(``require_token``) applies on top, same as ``/api/observations``. Nothing here
writes, emits or mutates state.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from typing import Any

from qoresence.truth.feed import TruthFeed, get_truth_feed

try:  # module-level so FastAPI can resolve the (postponed) ``Request`` annotation
    from fastapi import Request
except Exception:  # pragma: no cover - stdlib deck without fastapi
    Request = Any  # type: ignore[assignment,misc]

SSE_HEARTBEAT_S = 15.0
SSE_MAX_S = 3600.0


def lan_allowed() -> bool:
    return (os.getenv("QORESENCE_TRUTH_FEED_LAN") or "").strip().lower() in {"1", "true", "yes"}


def access_denied(*, client_host: str | None, token_ok: bool) -> tuple[int, dict[str, Any]] | None:
    from qoresence.security.redact import client_host_is_loopback

    if not token_ok:
        return 401, {"ok": False, "error": "unauthorized"}
    if client_host_is_loopback(client_host) or lan_allowed():
        return None
    return 403, {"ok": False, "error": "local_client_required"}


def _int(raw: Any, default: int | None) -> int | None:
    try:
        if raw is None or str(raw).strip() == "":
            return default
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _off() -> tuple[int, dict[str, Any]]:
    return 503, {
        "ok": False,
        "enabled": False,
        "error": "truth_feed_off",
        "hint": "start with --truth-feed or QORESENCE_TRUTH_FEED=1",
    }


def feed_body(params: dict[str, Any], feed: TruthFeed | None = None) -> tuple[int, dict[str, Any]]:
    f = feed if feed is not None else get_truth_feed()
    if f is None:
        return _off()
    since = _int(params.get("since"), None)
    limit = max(1, min(500, _int(params.get("limit"), 200) or 200))
    facts = f.recent(since=since, limit=limit)
    return 200, {
        "ok": True,
        "enabled": True,
        "schema": "qoresence.truth.fact.v0",
        "session_id": f.session_id,
        "signed": f.signer is not None,
        "next_seq": f.writer.next_seq,
        "facts": facts,
    }


def verify_body(feed: TruthFeed | None = None) -> tuple[int, dict[str, Any]]:
    f = feed if feed is not None else get_truth_feed()
    if f is None:
        return _off()
    try:
        out = f.verify()
    except Exception as e:
        return 500, {"ok": False, "error": f"verify_failed:{type(e).__name__}"}
    out["session_id"] = f.session_id
    return 200, out


def pubkey_body(feed: TruthFeed | None = None) -> tuple[int, dict[str, Any]]:
    f = feed if feed is not None else get_truth_feed()
    if f is None:
        return _off()
    s = f.signer
    return 200, {
        "ok": True,
        "signed": s is not None,
        "alg": "ed25519" if s is not None else None,
        "pubkey": s.pubkey_hex if s is not None else None,
        "key_id": s.key_id if s is not None else None,
        "sign_reason": f.sign_reason,
    }


def sse_events(
    params: dict[str, Any],
    *,
    last_event_id: str | None = None,
    feed: TruthFeed | None = None,
) -> Iterator[bytes]:
    """SSE generator. Ends after ``limit_s`` (default/max 3600 s)."""
    f = feed if feed is not None else get_truth_feed()
    if f is None:
        yield b'event: error\ndata: {"error":"truth_feed_off"}\n\n'
        return
    since = _int(params.get("since"), None)
    if since is None:
        since = _int(last_event_id, None)
    try:
        raw_ls = params.get("limit_s")
        limit_s = float(raw_ls) if raw_ls not in (None, "") else SSE_MAX_S
    except (TypeError, ValueError):
        limit_s = SSE_MAX_S
    limit_s = max(0.0, min(SSE_MAX_S, limit_s))
    deadline = time.monotonic() + limit_s
    last_beat = time.monotonic()
    yield b"retry: 3000\n\n"
    cursor = since if since is not None else -1
    while True:
        for rec in f.recent(since=cursor, limit=500):
            cursor = int(rec["seq"])
            data = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            yield f"id: {cursor}\nevent: fact\ndata: {data}\n\n".encode("ascii")
        now = time.monotonic()
        if now >= deadline:
            return
        if now - last_beat >= SSE_HEARTBEAT_S:
            last_beat = now
            yield b": ping\n\n"
        f.wait_for_new(min(1.0, max(0.05, deadline - now)))


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-store",
    "X-Accel-Buffering": "no",
}


def register_fastapi(app: Any) -> None:
    from fastapi.responses import JSONResponse, StreamingResponse

    def _guard(request: Request) -> Any | None:
        try:
            from qoresence.deck.server import _agent_check_token

            token_ok = bool(_agent_check_token(request))
        except Exception:
            token_ok = False
        host = getattr(getattr(request, "client", None), "host", None)
        denied = access_denied(client_host=host, token_ok=token_ok)
        if denied is not None:
            return JSONResponse(denied[1], status_code=denied[0])
        return None

    def _json(res: tuple[int, dict[str, Any]]) -> Any:
        return JSONResponse(res[1], status_code=res[0], headers={"Cache-Control": "no-store"})

    @app.get("/api/truth/feed")
    def api_truth_feed(request: Request):  # type: ignore[no-untyped-def]
        return _guard(request) or _json(feed_body(dict(request.query_params)))

    @app.get("/api/truth/verify")
    def api_truth_verify(request: Request):  # type: ignore[no-untyped-def]
        return _guard(request) or _json(verify_body())

    @app.get("/api/truth/pubkey")
    def api_truth_pubkey(request: Request):  # type: ignore[no-untyped-def]
        return _guard(request) or _json(pubkey_body())

    @app.get("/api/truth/stream")
    def api_truth_stream(request: Request):  # type: ignore[no-untyped-def]
        denied = _guard(request)
        if denied is not None:
            return denied
        if get_truth_feed() is None:
            return _json(_off())
        return StreamingResponse(
            sse_events(
                dict(request.query_params),
                last_event_id=request.headers.get("last-event-id"),
            ),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )


def handle_stdlib(handler: Any) -> bool:
    """Serve ``/api/truth/*`` from the stdlib deck. Returns True when handled."""
    from urllib.parse import parse_qsl, urlsplit

    parts = urlsplit(handler.path)
    if not parts.path.startswith("/api/truth/"):
        return False
    params = dict(parse_qsl(parts.query))

    class _Req:
        headers = handler.headers

    try:
        from qoresence.deck.server import _agent_check_token

        token_ok = bool(_agent_check_token(_Req()))
    except Exception:
        token_ok = False
    host = handler.client_address[0] if getattr(handler, "client_address", None) else None

    def _send(status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    denied = access_denied(client_host=host, token_ok=token_ok)
    if denied is not None:
        _send(*denied)
        return True
    route = parts.path
    if route == "/api/truth/feed":
        _send(*feed_body(params))
    elif route == "/api/truth/verify":
        _send(*verify_body())
    elif route == "/api/truth/pubkey":
        _send(*pubkey_body())
    elif route == "/api/truth/stream":
        if get_truth_feed() is None:
            _send(*_off())
            return True
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        for k, v in SSE_HEADERS.items():
            handler.send_header(k, v)
        handler.end_headers()
        try:
            for chunk in sse_events(params, last_event_id=handler.headers.get("Last-Event-ID")):
                handler.wfile.write(chunk)
                handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
    else:
        _send(404, {"ok": False, "error": "not_found"})
    return True
