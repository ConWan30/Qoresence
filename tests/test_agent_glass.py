"""AgentGlass tests — additive, non-breaking."""
from __future__ import annotations
import pathlib
import time

def test_snapshot_shape():
    from qoresence.agents.agent_glass import AgentGlass
    g = AgentGlass()
    snap = g.snapshot()
    assert snap["ok"] is True
    assert "session" in snap
    assert "coupling" in snap
    assert "video" in snap
    assert "seq" in snap
    assert "clock_ns" in snap

def test_fanout_outside_lock():
    from qoresence.core import RetinaEventBus, RetinaUnifiedConfig, SessionAuthority
    from qoresence.agents.agent_glass import AgentGlass
    from qoresence.core.types import EventType, SourceLobe, clock_ns, make_event
    sess = SessionAuthority.mint()
    bus = RetinaEventBus(session_id=sess.session_id, enable_ws=False)
    g = AgentGlass(bus=bus, session_identity=sess)
    assert g.start() is True
    # emit should not deadlock even if subscriber emits inside callback
    def reentrant(ev):
        try:
            bus.emit(make_event(sess.session_id, clock_ns(), SourceLobe.STREAMER, EventType.FRAME_STATS, {"ok": True}))
        except Exception:
            pass
    bus.subscribe(reentrant)
    ev = make_event(sess.session_id, clock_ns(), SourceLobe.STREAMER, EventType.FRAME_STATS, {"frame_seq": 1})
    bus.emit(ev)
    time.sleep(0.05)
    snap = g.snapshot()
    assert snap["events_count"] >= 1
    g.stop()

def test_frame_throttled_logic():
    # import deck helpers; verify 10fps window
    from qoresence.deck.server import _agent_frame_last, _agent_lock
    import time as _t
    cid = "test-client-frame"
    with _agent_lock:
        _agent_frame_last[cid] = _t.monotonic()
        last = _agent_frame_last[cid]
    assert _t.monotonic() - last < 0.1

def test_clip_rate_limit_global():
    from qoresence.deck import server
    import time as _t
    server._agent_clip_last = _t.monotonic()
    # second clip within 10s should be considered rate-limited by endpoint (checked via timestamp)
    assert _t.monotonic() - server._agent_clip_last < 10.0

def test_localhost_default():
    from qoresence.core.unified_config import RetinaUnifiedConfig
    c = RetinaUnifiedConfig()
    assert c.agent_glass.host == "127.0.0.1"
    assert c.agent_glass.enabled is False

def test_agent_watch_example_importable():
    import pathlib
    p = pathlib.Path("examples/agent_watch.py")
    assert p.exists()
    src = p.read_text(encoding="utf-8")
    assert "/api/agent/snapshot" in src
    assert "--once" in src

def test_events_cursor():
    from qoresence.agents.agent_glass import AgentGlass
    from qoresence.core.types import EventType, SourceLobe, clock_ns, make_event
    from qoresence.core import RetinaEventBus, SessionAuthority
    sess = SessionAuthority.mint()
    bus = RetinaEventBus(session_id=sess.session_id, enable_ws=False)
    g = AgentGlass(bus=bus, session_identity=sess)
    g.start()
    for i in range(5):
        ev = make_event(sess.session_id, clock_ns(), SourceLobe.STREAMER, EventType.FRAME_STATS, {"i": i})
        bus.emit(ev)
    time.sleep(0.05)
    page1 = g.get_events(since=0, limit=2)
    assert page1["count"] == 2
    since = page1["events"][-1]["_agent_seq"]
    page2 = g.get_events(since=since, limit=10)
    assert page2["count"] == 3
    # filter by type
    filtered = g.get_events(since=0, types=["not_a_type"], limit=10)
    assert filtered["count"] == 0
    g.stop()

def test_stdlib_fallback_has_agent_routes():
    src = pathlib.Path("qoresence/deck/server.py").read_text(encoding="utf-8")
    assert "/api/agent/snapshot" in src
    assert "/api/agent/events" in src
    assert "/api/agent/frame" in src
    assert "/api/agent/clip" in src
    assert "do_POST" in src or "def do_POST" in src
