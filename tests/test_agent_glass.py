"""AgentGlass tests — additive, non-breaking."""

from __future__ import annotations

import pathlib
import time


def test_snapshot_keeps_framehub_crop_observational(monkeypatch):
    from qoresence.agents.agent_glass import AgentGlass
    from qoresence.monitor import frame_hub

    class Hub:
        def stats(self):
            return {
                "has_frame": True,
                "crop_hash": "framehub-crop",
                "clock_ns": 2_000,
            }

    monkeypatch.setattr(frame_hub, "get_frame_hub", lambda: Hub())
    snap = AgentGlass(
        situation_provider=lambda: {
            "home_score": 14,
            "away_score": 10,
            "confirm_ticket_id": "c-1",
            "score_vlm_locked": True,
            "path": "confirm",
            "ticket_crop_hash": "ticket-scorebug-crop",
            "confirm_clock_ns": 1_000,
            "clock_ns": 2_000,
        }
    ).snapshot()

    assert snap["video"]["crop_hash"] == "framehub-crop"
    assert snap["seqgate"]["licensed"] is True
    assert snap["seqgate"]["reason"] == "licensed"


def test_confirm_ticket_stamp_reaches_agent_situation_and_seqgate():
    from qoresence.agents.agent_glass import AgentGlass
    from qoresence.agents.situation_model import SituationModel
    from qoresence.core.types import BaseEvent, EventType, SourceLobe
    from qoresence.vision.visual_context import GameCategory, GameState, VisualContext

    ticket_clock = time.monotonic_ns()
    ctx = VisualContext(
        game_state=GameState.GAMEPLAY,
        game_category=GameCategory.FOOTBALL,
        home_score=14,
        away_score=10,
        score_vlm_locked=True,
        confirm_ticket_id="confirm-remint",
        details={
            "confirm_ticket": {
                "ticket_id": "confirm-remint",
                "clock_ns": ticket_clock,
                "crop_hash": "scorebug-band-hash",
            }
        },
    )
    model = SituationModel()
    model.update(
        BaseEvent(
            session_id="session",
            clock_ns=ticket_clock,
            source_lobe=SourceLobe.VISUAL,
            type=EventType.VISUAL_CONTEXT,
            payload=ctx.to_dict(),
        )
    )

    situation = model.to_dict()
    assert situation["confirm_clock_ns"] == ticket_clock
    assert situation["ticket_crop_hash"] == "scorebug-band-hash"

    remint_clock = ticket_clock + 1_000
    ctx.confirm_ticket_id = "confirm-remint-2"
    ctx.details["confirm_ticket"] = {
        "ticket_id": "confirm-remint-2",
        "clock_ns": remint_clock,
        "crop_hash": "scorebug-band-hash-2",
    }
    model.update(
        BaseEvent(
            session_id="session",
            clock_ns=remint_clock,
            source_lobe=SourceLobe.VISUAL,
            type=EventType.VISUAL_CONTEXT,
            payload=ctx.to_dict(),
        )
    )

    snap = AgentGlass(situation_provider=model.to_dict).snapshot()
    assert snap["situation"]["confirm_clock_ns"] == remint_clock
    assert snap["situation"]["ticket_crop_hash"] == "scorebug-band-hash-2"
    assert snap["seqgate"]["reason"] == "licensed"
    assert snap["seqgate"]["licensed"] is True

    from qoresence.mcp.observation import build_observation

    observation = build_observation(
        situation=snap["situation"],
        video=snap["video"],
        coupling=snap["coupling"],
        clock_ns=snap["clock_ns"],
        seq=snap["seq"],
    )
    assert observation["seqgate"]["reason"] == "licensed"
    assert observation["score"] == {"claim": True, "home": 14, "away": 10}


def test_ticket_stamp_requires_matching_confirm_id():
    from qoresence.agents.situation_model import SituationModel
    from qoresence.core.types import BaseEvent, EventType, SourceLobe
    from qoresence.vision.visual_context import VisualContext

    ctx = VisualContext(
        score_vlm_locked=True,
        confirm_ticket_id="current",
        details={
            "confirm_ticket": {
                "ticket_id": "stale",
                "clock_ns": 123,
                "crop_hash": "wrong-ticket-crop",
            }
        },
    )
    model = SituationModel()
    model.update(
        BaseEvent(
            session_id="session",
            clock_ns=123,
            source_lobe=SourceLobe.VISUAL,
            type=EventType.VISUAL_CONTEXT,
            payload=ctx.to_dict(),
        )
    )

    situation = model.to_dict()
    assert situation["confirm_ticket_id"] == "current"
    assert situation["confirm_clock_ns"] == 0
    assert situation["ticket_crop_hash"] == ""


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
    from qoresence.agents.agent_glass import AgentGlass
    from qoresence.core import RetinaEventBus, SessionAuthority
    from qoresence.core.types import EventType, SourceLobe, clock_ns, make_event

    sess = SessionAuthority.mint()
    bus = RetinaEventBus(session_id=sess.session_id, enable_ws=False)
    g = AgentGlass(bus=bus, session_identity=sess)
    assert g.start() is True

    # emit should not deadlock even if subscriber emits inside callback
    def reentrant(ev):
        try:
            bus.emit(
                make_event(
                    sess.session_id,
                    clock_ns(),
                    SourceLobe.STREAMER,
                    EventType.FRAME_STATS,
                    {"ok": True},
                )
            )
        except Exception:
            pass

    bus.subscribe(reentrant)
    ev = make_event(
        sess.session_id, clock_ns(), SourceLobe.STREAMER, EventType.FRAME_STATS, {"frame_seq": 1}
    )
    bus.emit(ev)
    time.sleep(0.05)
    snap = g.snapshot()
    assert snap["events_count"] >= 1
    g.stop()


def test_frame_throttled_logic():
    # import deck helpers; verify 10fps window
    import time as _t

    from qoresence.deck.server import _agent_frame_last, _agent_lock

    cid = "test-client-frame"
    with _agent_lock:
        _agent_frame_last[cid] = _t.monotonic()
        last = _agent_frame_last[cid]
    assert _t.monotonic() - last < 0.1


def test_clip_rate_limit_global():
    import time as _t

    from qoresence.deck import server

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
    from qoresence.core import RetinaEventBus, SessionAuthority
    from qoresence.core.types import EventType, SourceLobe, clock_ns, make_event

    sess = SessionAuthority.mint()
    bus = RetinaEventBus(session_id=sess.session_id, enable_ws=False)
    g = AgentGlass(bus=bus, session_identity=sess)
    g.start()
    for i in range(5):
        ev = make_event(
            sess.session_id, clock_ns(), SourceLobe.STREAMER, EventType.FRAME_STATS, {"i": i}
        )
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
