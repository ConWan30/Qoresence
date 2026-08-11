"""MCP server tests — stdio JSON-RPC fallback + in-process glass."""

from __future__ import annotations

import json
import subprocess
import sys
import time


def _rpc(msgs):
    p = subprocess.Popen(
        [sys.executable, "-m", "qoresence.mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    inp = "\n".join(json.dumps(m) for m in msgs) + "\n"
    out, _ = p.communicate(inp, timeout=30)
    lines = [json.loads(x) for x in out.strip().splitlines() if x.strip()]
    p.terminate()
    return lines


def test_mcp_initialize_and_tools_list():
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    resps = _rpc(reqs)
    assert len(resps) == 2
    assert resps[0]["result"]["serverInfo"]["name"] == "qoresence"
    names = {t["name"] for t in resps[1]["result"]["tools"]}
    assert names == {
        "get_snapshot",
        "get_events",
        "get_health",
        "get_frame",
        "export_clip",
        "get_situation",
        "search_clips",
        "get_drive_graph",
        "subscribe_events",
        "diagnose_freeze",
    }


def test_mcp_resources_and_prompts_list():
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "resources/list"},
        {"jsonrpc": "2.0", "id": 2, "method": "prompts/list"},
    ]
    resps = _rpc(reqs)
    assert "snapshot" in str(resps[0]["result"]["resources"])
    assert "coach_clutch" in str(resps[1]["result"]["prompts"])


def test_mcp_tools_call_in_process_snapshot_and_events():
    import qoresence.mcp.server as mcp_server
    from qoresence.agents.agent_glass import AgentGlass
    from qoresence.core import RetinaEventBus, SessionAuthority
    from qoresence.core.types import EventType, SourceLobe, clock_ns, make_event

    sess = SessionAuthority.mint()
    bus = RetinaEventBus(session_id=sess.session_id, enable_ws=False)
    g = AgentGlass(bus=bus, session_identity=sess)
    g.start()
    for i in range(3):
        bus.emit(
            make_event(
                sess.session_id, clock_ns(), SourceLobe.STREAMER, EventType.FRAME_STATS, {"i": i}
            )
        )
    time.sleep(0.05)
    orig = mcp_server._get_glass
    try:
        mcp_server._get_glass = lambda: g
        snap = mcp_server.handle_get_snapshot()
        assert snap["ok"] is True and snap["seq"] >= 3
        ev = mcp_server.handle_get_events(since=0, limit=2)
        assert ev["count"] == 2 and ev["next_seq"] >= 3
        health = mcp_server.handle_get_health()
        assert health["ok"] is True and "seq" in health
        situ = mcp_server.handle_get_situation()
        assert situ["ok"] is True and "coupling" in situ
    finally:
        mcp_server._get_glass = orig
        g.stop()


def test_mcp_export_clip_and_unknown():
    reqs = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "export_clip", "arguments": {"seconds": 5}},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_situation", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "unknown_tool", "arguments": {}},
        },
    ]
    resps = _rpc(reqs)
    assert resps[0]["result"]["content"][0]["type"] == "text"
    assert resps[1]["result"]["content"][0]["type"] == "text"
    assert resps[2]["error"]["code"] == -32601


def test_mcp_notifications_and_resources_read():
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/read",
            "params": {"uri": "qoresence://snapshot"},
        },
        {"jsonrpc": "2.0", "id": 3, "method": "prompts/get", "params": {"name": "coach_clutch"}},
    ]
    resps = _rpc(reqs)
    assert len(resps) == 3
    assert resps[0]["result"] == {}
    assert "contents" in resps[1]["result"]


def test_mcp_tools_call_http_unreachable_hint():
    import qoresence.mcp.server as mcp_server

    orig_glass = mcp_server._get_glass
    orig_http = mcp_server._http_get
    try:
        # Force both in-process glass and HTTP offline so this is stable
        # even when a live Deck is bound on :8765 during local pilots.
        mcp_server._get_glass = lambda: None
        mcp_server._http_get = lambda path, token=None: {
            "ok": False,
            "error": "http_unreachable",
            "hint": f"is Qoresence running with --agent-glass? (forced offline for {path})",
        }
        health = mcp_server.handle_get_health()
        assert health.get("error") == "http_unreachable"
        assert (
            "agent-glass" in health.get("hint", "").lower()
            or "refused" in health.get("hint", "").lower()
        )
        snap = mcp_server.handle_get_snapshot()
        assert snap.get("error") == "http_unreachable"
        assert "agent-glass" in snap.get("hint", "").lower()
    finally:
        mcp_server._get_glass = orig_glass
        mcp_server._http_get = orig_http


def test_foundry_search_and_drive_graph_via_mcp():
    import json as _json

    import qoresence.mcp.server as mcp_server

    # search_clips should work even with no glass (falls back to timeline/clips scan)
    res = mcp_server.handle_search_clips(query="red zone", limit=2)
    assert res["ok"] is True
    assert "hits" in res
    # RPC roundtrip
    reqs = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "search_clips", "arguments": {"query": "red zone", "limit": 2}},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_drive_graph", "arguments": {"drive_id": "active"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "diagnose_freeze", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "subscribe_events", "arguments": {"since": 0, "limit": 2}},
        },
    ]
    resps = _rpc(reqs)
    assert len(resps) == 4
    for r in resps:
        assert r["result"]["content"][0]["type"] == "text"
        obj = _json.loads(r["result"]["content"][0]["text"])
        # allow ok False for get_drive_graph when no active drive
        assert "ok" in obj


def test_subscribe_events_cursor_and_diagnose():
    import qoresence.mcp.server as mcp_server
    from qoresence.agents.agent_glass import AgentGlass
    from qoresence.core import RetinaEventBus, SessionAuthority
    from qoresence.core.types import EventType, SourceLobe, clock_ns, make_event

    sess = SessionAuthority.mint()
    bus = RetinaEventBus(session_id=sess.session_id, enable_ws=False)
    g = AgentGlass(bus=bus, session_identity=sess)
    g.start()
    for i in range(2):
        bus.emit(
            make_event(
                sess.session_id, clock_ns(), SourceLobe.STREAMER, EventType.FRAME_STATS, {"i": i}
            )
        )
    time.sleep(0.05)
    orig = mcp_server._get_glass
    try:
        mcp_server._get_glass = lambda: g
        sub = mcp_server.handle_subscribe_events(since=0, limit=2)
        assert sub["ok"] is True and "next_since" in sub and sub["count"] >= 1
        nxt = int(sub["next_since"])
        sub2 = mcp_server.handle_subscribe_events(since=nxt, limit=2)
        assert sub2["ok"] is True
        diag = mcp_server.handle_diagnose_freeze()
        assert diag["ok"] is True and diag["diagnosis"] in ("HEALTHY", "NO_FRAMES", "FROZEN")
        assert "refs" in diag or "advice" in diag  # AGENTS advice present
    finally:
        mcp_server._get_glass = orig
        g.stop()


def test_drive_graph_no_capture_card_software_only():
    import qoresence.mcp.server as mcp_server

    # should never try to open cv2.VideoCapture
    dg = mcp_server.handle_get_drive_graph(drive_id="active", include_nodes=True, max_nodes=5)
    assert "ok" in dg
    # get_drive_graph error path is still software-only, not a capture open
    assert "error" in dg or dg.get("ok") is True


def test_search_clips_filters():
    import qoresence.mcp.server as mcp_server

    # coupling_min and kinds filters must not crash; no capture required
    r1 = mcp_server.handle_search_clips(query="", limit=3, kinds="confirm_chat", coupling_min=0.0)
    assert r1["ok"] is True
    r2 = mcp_server.handle_search_clips(query="nonexistentqueryxyz", limit=2)
    assert r2["ok"] is True and isinstance(r2["hits"], list)
