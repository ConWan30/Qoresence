#!/usr/bin/env python3
"""Agent watcher demo — external spectator for Qoresence AgentGlass (glass D).

Reads the unified PS5 HDMI + input + game-state timeline via
RetinaEventBus/Deck without ever opening capture. Localhost only.

Usage:
  # one-shot snapshot (CI friendly)
  python examples/agent_watch.py --once
  # live tail (polling every 0.5s; use --ws for websocket if websockets installed)
  python examples/agent_watch.py
  python examples/agent_watch.py --ws
  python examples/agent_watch.py --types presence_report,visual_context --limit 20

Requires Qoresence running with AgentGlass enabled:
  set QORESENCE_AGENT_GLASS_ENABLED=1
  python -m qoresence.cli --play --deck --agent-glass
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _url(host: str, port: int, path: str) -> str:
    return f"http://{host}:{port}{path}"


def fetch_json(host: str, port: int, path: str, token: str | None = None) -> dict:
    url = _url(host, port, path)
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description="Qoresence AgentGlass watcher")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--token", default=None, help="Bearer token if require_token=true")
    p.add_argument("--once", action="store_true", help="fetch snapshot+events once and exit")
    p.add_argument("--ws", action="store_true", help="use WS /agent/stream if websockets installed")
    p.add_argument("--types", default=None, help="comma-separated event types filter")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--snapshot-only", action="store_true")
    args = p.parse_args()

    try:
        snap = fetch_json(args.host, args.port, "/api/agent/snapshot", token=args.token)
    except Exception as e:
        print(
            f"snapshot fetch failed: {e} (is Qoresence running with --agent-glass?)",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(snap, indent=2))
    if args.snapshot_only or args.once:
        if not args.snapshot_only:
            # also show events
            qs = f"?since=0&limit={args.limit}"
            if args.types:
                qs += f"&types={urllib.parse.quote(args.types)}"
            try:
                ev = fetch_json(args.host, args.port, f"/api/agent/events{qs}", token=args.token)
                print("\n--- events ---")
                print(json.dumps(ev, indent=2))
            except Exception as e:
                print(f"events fetch failed: {e}", file=sys.stderr)
        return 0

    if args.ws:
        try:
            import websockets  # type: ignore

            async def _ws_run():
                uri = f"ws://{args.host}:{args.port}/agent/stream"
                if args.token:
                    uri += f"?token={urllib.parse.quote(args.token)}"
                print(f"WS {uri} ...", file=sys.stderr)
                async with websockets.connect(uri) as ws:
                    async for msg in ws:
                        try:
                            obj = json.loads(msg)
                        except Exception:
                            print(msg)
                            continue
                        print(json.dumps(obj)[:600])

            import asyncio as _aio

            _aio.run(_ws_run())
            return 0
        except ImportError:
            print("websockets not installed, falling back to polling", file=sys.stderr)
        except Exception as e:
            print(f"ws failed: {e}", file=sys.stderr)
            return 1

    # polling tail
    since = int(snap.get("seq", 0) or 0)
    print(f"\nTailing events since={since} (Ctrl+C to stop) ...", file=sys.stderr)
    while True:
        time.sleep(0.5)
        qs = f"?since={since}&limit={args.limit}"
        if args.types:
            qs += f"&types={urllib.parse.quote(args.types)}"
        try:
            ev = fetch_json(args.host, args.port, f"/api/agent/events{qs}", token=args.token)
        except Exception as e:
            print(f"poll failed: {e}", file=sys.stderr)
            continue
        for e in ev.get("events", []):
            seq = e.get("_agent_seq", "?")
            typ = e.get("type", "?")
            print(f"[{seq}] {typ} {json.dumps(e.get('payload', {}))[:300]}")
        since = int(ev.get("next_seq", since))


if __name__ == "__main__":
    raise SystemExit(main())
