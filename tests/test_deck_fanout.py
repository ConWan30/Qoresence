"""Deck fanout must stay bounded when clients are slow."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque

from qoresence.deck import server


class _LoopProbe:
    def __init__(self) -> None:
        self.scheduled = 0

    def call_soon_threadsafe(self, callback) -> None:
        self.scheduled += 1


def test_broadcast_coalesces_situations_and_bounds_pending(monkeypatch):
    loop = _LoopProbe()
    monkeypatch.setattr(server, "_loop", loop)
    monkeypatch.setattr(server, "_broadcast_pending", deque(maxlen=64))
    monkeypatch.setattr(server, "_broadcast_scheduled", False)

    for score in range(1000):
        server._broadcast({"type": "situation", "payload": {"home_score": score}})

    assert len(server._broadcast_pending) == 1
    assert server._broadcast_pending[0]["payload"]["home_score"] == 999
    assert loop.scheduled == 1

    for index in range(100):
        server._broadcast({"type": "moment", "payload": {"title": str(index)}})

    assert len(server._broadcast_pending) <= 64


def test_broadcast_delivery_replaces_oldest_slow_client_message():
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
    queue.put_nowait("old-1")
    queue.put_nowait("old-2")

    server._enqueue_ws_message(queue, "latest")

    assert queue.qsize() == 2
    assert queue.get_nowait() == "old-2"
    assert queue.get_nowait() == "latest"


def test_broadcast_drain_delivers_json_without_blocking_producer(monkeypatch):
    async def _run() -> None:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
        client = object()
        monkeypatch.setattr(server, "_loop", asyncio.get_running_loop())
        monkeypatch.setattr(server, "_ws_queues", {client: queue})
        monkeypatch.setattr(server, "_broadcast_pending", deque(maxlen=64))
        monkeypatch.setattr(server, "_broadcast_scheduled", False)

        started = time.monotonic()
        for index in range(100):
            server._broadcast({"type": "situation", "payload": {"home_score": index}})
        producer_elapsed = time.monotonic() - started
        await asyncio.sleep(0)

        delivered = json.loads(await queue.get())
        assert delivered["payload"]["home_score"] == 99
        assert producer_elapsed < 0.5

    asyncio.run(_run())
