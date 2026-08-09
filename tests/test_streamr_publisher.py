"""Tests for Streamr publisher integration."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from qoresence.core import BaseEvent, EventType, RetinaEventBus, SessionAuthority, SourceLobe
from qoresence.core.unified_config import StreamrConfig
from qoresence.streamr.publisher import StreamrPublisher, make_streamr_publisher_from_config


def _make_bus(tmp_path: Path) -> RetinaEventBus:
    identity = SessionAuthority.mint(session_id="streamr_test")
    return RetinaEventBus(
        session_id=identity.session_id,
        jsonl_path=tmp_path / "events.jsonl",
        enable_ws=False,
    )


class _FakeStreamrHandler(BaseHTTPRequestHandler):
    """Minimal HTTP plugin mock for Streamr node."""

    received: list[tuple[str, bytes]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _FakeStreamrHandler.received.append((self.path, body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args) -> None:
        pass


def _run_fake_server(port: int) -> HTTPServer:
    _FakeStreamrHandler.received = []
    server = HTTPServer(("127.0.0.1", port), _FakeStreamrHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def test_factory_returns_none_when_disabled():
    cfg = StreamrConfig(enabled=False)
    assert make_streamr_publisher_from_config(cfg) is None


def test_publisher_ignores_unconfigured_stream():
    cfg = StreamrConfig(enabled=True, stream_id="")
    pub = make_streamr_publisher_from_config(cfg)
    assert pub is None


def test_http_publisher_posts_to_streamr_node(tmp_path):
    port = 17171
    server = _run_fake_server(port)
    try:
        cfg = StreamrConfig(
            enabled=True,
            stream_id="0xtest/qoresence/football",
            protocol="http",
            host="127.0.0.1",
            port=port,
            event_types=["*"],
        )
        pub = StreamrPublisher(cfg)

        bus = _make_bus(tmp_path)
        bus.emit(
            BaseEvent(
                session_id=bus.session_id,
                source_lobe=SourceLobe.STREAMER,
                type=EventType.PRESENCE_REPORT,
                payload={"verdict": "gameplay"},
                clock_ns=time.monotonic_ns(),
            )
        )

        # Trigger the publisher synchronously via the bus it is normally wired to.
        pub.publish(
            BaseEvent(
                session_id=bus.session_id,
                source_lobe=SourceLobe.STREAMER,
                type=EventType.PRESENCE_REPORT,
                payload={"verdict": "gameplay"},
                clock_ns=time.monotonic_ns(),
            )
        )

        # Wait for background worker to flush
        for _ in range(50):
            if _FakeStreamrHandler.received:
                break
            time.sleep(0.05)

        assert len(_FakeStreamrHandler.received) == 1
        path, body = _FakeStreamrHandler.received[0]
        assert path == "/streams/0xtest%2Fqoresence%2Ffootball"
        data = json.loads(body.decode("utf-8"))
        assert data["type"] == "presence_report"
        assert data["payload"]["verdict"] == "gameplay"
    finally:
        pub.stop()
        server.shutdown()


def test_publisher_respects_event_type_filter(tmp_path):
    port = 17172
    server = _run_fake_server(port)
    try:
        cfg = StreamrConfig(
            enabled=True,
            stream_id="0xtest/qoresence/football",
            protocol="http",
            host="127.0.0.1",
            port=port,
            event_types=["visual_context"],
        )
        pub = StreamrPublisher(cfg)

        for et in ("frame_stats", "visual_context"):
            pub.publish(
                BaseEvent(
                    session_id="streamr_filter_test",
                    source_lobe=SourceLobe.STREAMER,
                    type=EventType(et),
                    payload={"ok": True},
                    clock_ns=time.monotonic_ns(),
                )
            )

        for _ in range(50):
            if _FakeStreamrHandler.received:
                break
            time.sleep(0.05)

        assert len(_FakeStreamrHandler.received) == 1
        path, body = _FakeStreamrHandler.received[0]
        assert b'"type": "visual_context"' in body
    finally:
        pub.stop()
        server.shutdown()


def test_publisher_gracefully_fails_when_node_down(tmp_path):
    cfg = StreamrConfig(
        enabled=True,
        stream_id="0xtest/qoresence/football",
        protocol="http",
        host="127.0.0.1",
        port=17173,  # nothing listening
        event_types=["*"],
        timeout_s=0.25,
    )
    pub = StreamrPublisher(cfg)
    # Should not raise even though the server is down.
    pub.publish(
        BaseEvent(
            session_id="streamr_fail_test",
            source_lobe=SourceLobe.STREAMER,
            type=EventType.PRESENCE_REPORT,
            payload={"verdict": "gameplay"},
            clock_ns=time.monotonic_ns(),
        )
    )
    time.sleep(0.3)
    pub.stop()
